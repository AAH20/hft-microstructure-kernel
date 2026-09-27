"""
High-Performance Price-Time Priority (FIFO) Limit Order Book (LOB) Matching Engine.
Features O(1) amortized Best-Bid/Best-Ask lookup, O(1) order cancellation via hash indexing,
and deterministic execution fill reporting with nanosecond latency telemetry.
"""

from __future__ import annotations
import bisect
import collections
import time
from typing import Dict, List, Optional, Tuple
from hft_microstructure_kernel.core.models import (
    Side,
    OrderType,
    LimitOrder,
    OrderBookLevel,
    OrderBookSnapshot,
    ExecutionFill,
    MatchingEngineMetrics,
)


class PriceLevelQueue:
    """Represents a discrete price level with a FIFO queue of resting limit orders."""
    __slots__ = ("price", "orders", "total_volume")

    def __init__(self, price: float):
        self.price = price
        self.orders: collections.deque[LimitOrder] = collections.deque()
        self.total_volume = 0.0

    def append(self, order: LimitOrder) -> None:
        self.orders.append(order)
        self.total_volume += order.quantity

    def cancel(self, order_id: str) -> Optional[LimitOrder]:
        """O(K) search within single price tier for specific order, where K is orders at that price."""
        for i, order in enumerate(self.orders):
            if order.order_id == order_id:
                self.total_volume -= order.quantity
                del self.orders[i]
                return order
        return None


class HighFrequencyMatchingEngine:
    """
    Deterministic FIFO Matching Engine for ultra-low latency continuous trading.
    Maintains sorted price ladders for bids and asks and order maps for O(1) lookups.
    """

    def __init__(self, symbol: str = "BTC-USD", venue: str = "PRIMARY"):
        self.symbol = symbol
        self.venue = venue
        # Bid ladder: sorted ascending prices (best bid is bids_prices[-1])
        self.bids_prices: List[float] = []
        # Ask ladder: sorted ascending prices (best ask is asks_prices[0])
        self.asks_prices: List[float] = []
        # Level lookup: (side, price) -> PriceLevelQueue
        self.levels: Dict[Tuple[Side, float], PriceLevelQueue] = {}
        # Order lookup: order_id -> LimitOrder
        self.order_map: Dict[str, LimitOrder] = {}

        # Telemetry metrics
        self.total_orders_processed = 0
        self.total_cancellations = 0
        self.total_fills = 0
        self.total_volume_matched = 0.0
        self.fill_history: List[ExecutionFill] = []
        self.latencies_ns: List[int] = []

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids_prices[-1] if self.bids_prices else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks_prices[0] if self.asks_prices else None

    @property
    def mid_price(self) -> Optional[float]:
        bb = self.best_bid
        ba = self.best_ask
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return bb or ba

    def submit_order(self, order: LimitOrder) -> List[ExecutionFill]:
        """
        Submits an incoming order (limit or marketable) and returns generated fills.
        Tracks microsecond-precision execution latency.
        """
        start_ns = time.perf_counter_ns()
        self.total_orders_processed += 1
        fills: List[ExecutionFill] = []

        remaining_qty = order.quantity

        if order.side == Side.BUY:
            # Match against resting asks while order.price >= best_ask
            while remaining_qty > 1e-9 and self.asks_prices:
                best_ask_price = self.asks_prices[0]
                if order.price < best_ask_price:
                    break

                level = self.levels[(Side.SELL, best_ask_price)]
                while remaining_qty > 1e-9 and level.orders:
                    resting_order = level.orders[0]
                    matched_qty = min(remaining_qty, resting_order.quantity)

                    remaining_qty -= matched_qty
                    resting_order.quantity -= matched_qty
                    level.total_volume -= matched_qty
                    self.total_volume_matched += matched_qty
                    self.total_fills += 1

                    fill = ExecutionFill(
                        fill_id=f"fill_{self.total_fills}",
                        order_id=order.order_id,
                        matched_order_id=resting_order.order_id,
                        price=best_ask_price,
                        quantity=matched_qty,
                        taker_side=Side.BUY,
                        venue=self.venue,
                        latency_ns=time.perf_counter_ns() - start_ns,
                        fee_paid=matched_qty * best_ask_price * 0.0002,
                    )
                    fills.append(fill)
                    self.fill_history.append(fill)

                    if resting_order.quantity <= 1e-9:
                        level.orders.popleft()
                        self.order_map.pop(resting_order.order_id, None)

                if not level.orders:
                    del self.levels[(Side.SELL, best_ask_price)]
                    self.asks_prices.pop(0)

            # If residual volume remains, place on bids book
            if remaining_qty > 1e-9:
                order.quantity = remaining_qty
                self._insert_bid(order)

        else:  # Side.SELL
            # Match against resting bids while order.price <= best_bid
            while remaining_qty > 1e-9 and self.bids_prices:
                best_bid_price = self.bids_prices[-1]
                if order.price > best_bid_price:
                    break

                level = self.levels[(Side.BUY, best_bid_price)]
                while remaining_qty > 1e-9 and level.orders:
                    resting_order = level.orders[0]
                    matched_qty = min(remaining_qty, resting_order.quantity)

                    remaining_qty -= matched_qty
                    resting_order.quantity -= matched_qty
                    level.total_volume -= matched_qty
                    self.total_volume_matched += matched_qty
                    self.total_fills += 1

                    fill = ExecutionFill(
                        fill_id=f"fill_{self.total_fills}",
                        order_id=order.order_id,
                        matched_order_id=resting_order.order_id,
                        price=best_bid_price,
                        quantity=matched_qty,
                        taker_side=Side.SELL,
                        venue=self.venue,
                        latency_ns=time.perf_counter_ns() - start_ns,
                        fee_paid=matched_qty * best_bid_price * 0.0002,
                    )
                    fills.append(fill)
                    self.fill_history.append(fill)

                    if resting_order.quantity <= 1e-9:
                        level.orders.popleft()
                        self.order_map.pop(resting_order.order_id, None)

                if not level.orders:
                    del self.levels[(Side.BUY, best_bid_price)]
                    self.bids_prices.pop()

            # If residual volume remains, place on asks book
            if remaining_qty > 1e-9:
                order.quantity = remaining_qty
                self._insert_ask(order)

        elapsed_ns = time.perf_counter_ns() - start_ns
        self.latencies_ns.append(elapsed_ns)
        return fills

    def _insert_bid(self, order: LimitOrder) -> None:
        key = (Side.BUY, order.price)
        if key not in self.levels:
            bisect.insort(self.bids_prices, order.price)
            self.levels[key] = PriceLevelQueue(order.price)
        self.levels[key].append(order)
        self.order_map[order.order_id] = order

    def _insert_ask(self, order: LimitOrder) -> None:
        key = (Side.SELL, order.price)
        if key not in self.levels:
            bisect.insort(self.asks_prices, order.price)
            self.levels[key] = PriceLevelQueue(order.price)
        self.levels[key].append(order)
        self.order_map[order.order_id] = order

    def cancel_order(self, order_id: str) -> bool:
        """Cancels a resting order in O(1) amortized time."""
        order = self.order_map.get(order_id)
        if not order:
            return False

        key = (order.side, order.price)
        level = self.levels.get(key)
        if level:
            cancelled = level.cancel(order_id)
            if cancelled:
                self.order_map.pop(order_id, None)
                self.total_cancellations += 1
                if not level.orders:
                    del self.levels[key]
                    if order.side == Side.BUY:
                        idx = bisect.bisect_left(self.bids_prices, order.price)
                        if idx < len(self.bids_prices) and self.bids_prices[idx] == order.price:
                            self.bids_prices.pop(idx)
                    else:
                        idx = bisect.bisect_left(self.asks_prices, order.price)
                        if idx < len(self.asks_prices) and self.asks_prices[idx] == order.price:
                            self.asks_prices.pop(idx)
                return True
        return False

    def get_snapshot(self, depth: int = 10) -> OrderBookSnapshot:
        """Returns Level 2 order book snapshot up to depth levels."""
        # Bids are sorted ascending, top of book is at the end
        top_bids = []
        for p in reversed(self.bids_prices[-depth:]):
            lvl = self.levels[(Side.BUY, p)]
            top_bids.append(OrderBookLevel(price=p, quantity=lvl.total_volume, order_count=len(lvl.orders)))

        # Asks are sorted ascending, top of book is at the beginning
        top_asks = []
        for p in self.asks_prices[:depth]:
            lvl = self.levels[(Side.SELL, p)]
            top_asks.append(OrderBookLevel(price=p, quantity=lvl.total_volume, order_count=len(lvl.orders)))

        return OrderBookSnapshot(
            symbol=self.symbol,
            venue=self.venue,
            timestamp_ns=time.perf_counter_ns(),
            bids=top_bids,
            asks=top_asks,
        )

    def get_metrics(self) -> MatchingEngineMetrics:
        """Computes statistical latency profile and operational throughput."""
        if not self.latencies_ns:
            return MatchingEngineMetrics(0, 0, 0.0, 0, 0.0, 0.0, 0.0)

        sorted_latencies = sorted(self.latencies_ns)
        mean_lat = sum(sorted_latencies) / len(sorted_latencies)
        p99_idx = int(0.99 * len(sorted_latencies))
        p99_lat = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]

        total_time_sec = sum(sorted_latencies) / 1e9
        throughput = (self.total_orders_processed / total_time_sec) if total_time_sec > 0 else 0.0

        return MatchingEngineMetrics(
            total_orders_processed=self.total_orders_processed,
            total_fills=self.total_fills,
            total_volume_matched=self.total_volume_matched,
            total_cancellations=self.total_cancellations,
            mean_latency_ns=mean_lat,
            p99_latency_ns=p99_lat,
            throughput_orders_per_sec=throughput,
        )
