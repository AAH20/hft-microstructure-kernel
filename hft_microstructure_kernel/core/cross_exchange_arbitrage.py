"""
Cross-Exchange & Triangular Arbitrage Solver with Non-Linear Depth Slippage.
Formulated via -log(p) Negative Cycle Detection (Bellman-Ford / Cycle Search)
with dynamic order-book volume exhaustion and latency risk penalties.
"""

from __future__ import annotations
import math
import time
from typing import List, Dict, Tuple, Optional
from hft_microstructure_kernel.core.models import (
    ExchangeLiquidityPool,
    ArbitrageVenue,
    ArbitrageCycle,
    ArbitrageReport,
)


class CrossExchangeArbitrageSolver:
    """
    High-frequency cross-exchange arbitrage detector.
    Identifies negative cycles in log-price graph across multiple venues and assets,
    then solves for optimal volume extraction under non-linear square-root market impact
    and venue latency penalties.
    """

    def __init__(
        self,
        venues: Dict[str, ArbitrageVenue],
        pools: List[ExchangeLiquidityPool],
        latency_risk_coef: float = 0.000001,  # Risk discount per microsecond of execution latency
    ):
        self.venues = venues
        self.pools = pools
        self.latency_risk_coef = latency_risk_coef
        self.assets: set[str] = set()
        for p in self.pools:
            self.assets.add(p.base_asset)
            self.assets.add(p.quote_asset)

    def _build_directed_edges(self) -> List[Tuple[str, str, str, float, float, float, float]]:
        """
        Build directed graph edges: (from_asset, to_asset, venue_id, base_rate, max_depth, slippage_factor, latency_us)
        Selling base -> quote: rate = bid_price * (1 - taker_fee)
        Buying base <- quote: rate = (1 / ask_price) * (1 - taker_fee)
        """
        edges = []
        for pool in self.pools:
            venue = self.venues.get(pool.venue_id)
            fee_taker = (venue.fee_taker_bps / 10000.0) if venue else 0.0005
            latency_us = venue.latency_us if venue else 50.0

            # Sell base for quote (e.g., BTC -> USD at bid_price)
            if pool.bid_price > 0 and pool.bid_depth > 0:
                net_rate = pool.bid_price * (1.0 - fee_taker)
                edges.append((
                    pool.base_asset,
                    pool.quote_asset,
                    pool.venue_id,
                    net_rate,
                    pool.bid_depth,
                    pool.slippage_factor,
                    latency_us,
                ))

            # Buy base with quote (e.g., USD -> BTC at 1/ask_price)
            if pool.ask_price > 0 and pool.ask_depth > 0:
                net_rate = (1.0 / pool.ask_price) * (1.0 - fee_taker)
                edges.append((
                    pool.quote_asset,
                    pool.base_asset,
                    pool.venue_id,
                    net_rate,
                    pool.ask_depth * pool.ask_price,  # Depth in quote asset terms
                    pool.slippage_factor,
                    latency_us,
                ))
        return edges

    def find_arbitrage_cycles(self, base_currency: str = "USD", max_hops: int = 4) -> ArbitrageReport:
        """
        Executes negative-cycle search originating from base_currency up to max_hops.
        Optimizes trade size V to maximize profit subject to order-book depth.
        """
        start_time = time.perf_counter()
        edges = self._build_directed_edges()

        # Build adjacency mapping: from_node -> list of edges
        adj: Dict[str, List[Tuple[str, str, float, float, float, float]]] = {}
        for u, v, ven, rate, depth, slip, lat in edges:
            if u not in adj:
                adj[u] = []
            adj[u].append((v, ven, rate, depth, slip, lat))

        found_cycles: List[ArbitrageCycle] = []
        total_scanned = 0

        # Depth-First Search for simple cycles starting and ending at base_currency
        def dfs(current: str, path: List[str], venues_used: List[str], current_edges: List[Tuple[float, float, float, float]], visited: set):
            nonlocal total_scanned
            if len(path) > max_hops + 1:
                return

            if len(path) > 2 and current == base_currency:
                total_scanned += 1
                cycle = self._evaluate_cycle(path, venues_used, current_edges)
                if cycle.is_profitable:
                    found_cycles.append(cycle)
                return

            if current not in adj:
                return

            for next_node, ven, rate, depth, slip, lat in adj[current]:
                if next_node == base_currency or next_node not in visited:
                    visited.add(next_node)
                    dfs(
                        next_node,
                        path + [next_node],
                        venues_used + [ven],
                        current_edges + [(rate, depth, slip, lat)],
                        visited,
                    )
                    if next_node != base_currency:
                        visited.remove(next_node)

        visited_set = {base_currency}
        dfs(base_currency, [base_currency], [], [], visited_set)

        # Sort found cycles by net profit USD descending
        found_cycles.sort(key=lambda c: c.net_profit_usd, reverse=True)
        max_profit = found_cycles[0].net_profit_usd if found_cycles else 0.0
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return ArbitrageReport(
            total_cycles_scanned=total_scanned,
            profitable_cycles=found_cycles,
            max_profit_usd=max_profit,
            execution_time_ms=elapsed_ms,
        )

    def _evaluate_cycle(
        self,
        path: List[str],
        venues: List[str],
        edge_data: List[Tuple[float, float, float, float]],
    ) -> ArbitrageCycle:
        """
        Evaluates a specific cycle by computing gross return and optimizing executable volume.
        edge_data contains: (base_rate, max_depth, slippage_factor, latency_us)
        """
        # Gross return for infinitesimal size (no slippage)
        gross_return = 1.0
        total_latency = 0.0
        min_depth = float("inf")

        for rate, depth, slip, lat in edge_data:
            gross_return *= rate
            total_latency += lat
            if depth < min_depth:
                min_depth = depth

        # Gross return in bps relative to 1.0
        gross_bps = (gross_return - 1.0) * 10000.0

        if gross_return <= 1.0:
            return ArbitrageCycle(
                path=path,
                venues=venues,
                gross_return_ratio=gross_return,
                net_return_bps=gross_bps,
                executable_volume=0.0,
                net_profit_usd=0.0,
                total_latency_us=total_latency,
                is_profitable=False,
            )

        # Optimal trade size search via Golden Section Search on [0, min_depth]
        # PnL(V) = V * (Product_i(rate_i * (1 - slip_i * sqrt(V_i))) - 1) - LatencyPenalty
        def objective(v: float) -> float:
            if v <= 0.0:
                return 0.0
            mult = 1.0
            for rate, depth, slip, lat in edge_data:
                # Effective slippage on leg
                leg_slip = slip * math.sqrt(min(v, depth) / max(1.0, depth))
                mult *= (rate * (1.0 - leg_slip))
            net_gain = v * (mult - 1.0)
            latency_discount = v * (total_latency * self.latency_risk_coef)
            return net_gain - latency_discount

        # Ternary search for unimodal function
        low = 100.0
        high = min(min_depth, 1_000_000.0)
        best_v = 0.0
        best_pnl = 0.0

        if high > low:
            for _ in range(25):
                m1 = low + (high - low) / 3.0
                m2 = high - (high - low) / 3.0
                p1 = objective(m1)
                p2 = objective(m2)
                if p1 < p2:
                    low = m1
                else:
                    high = m2
            best_v = (low + high) / 2.0
            best_pnl = objective(best_v)

        is_prof = best_pnl > 0.0
        net_bps = (best_pnl / best_v * 10000.0) if best_v > 0 else gross_bps

        return ArbitrageCycle(
            path=path,
            venues=venues,
            gross_return_ratio=gross_return,
            net_return_bps=net_bps,
            executable_volume=best_v if is_prof else 0.0,
            net_profit_usd=max(0.0, best_pnl),
            total_latency_us=total_latency,
            is_profitable=is_prof,
        )
