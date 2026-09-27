"""
Data models and typed structures for Quantitative HFT & Market Microstructure Kernel.
Zero external pip dependencies. Strict Python 3.10+ typing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    CANCEL = "CANCEL"


@dataclass(slots=True)
class LimitOrder:
    order_id: str
    symbol: str
    side: Side
    price: float
    quantity: float
    timestamp_ns: int
    venue: str = "PRIMARY"


@dataclass(slots=True)
class OrderBookLevel:
    price: float
    quantity: float
    order_count: int


@dataclass(slots=True)
class OrderBookSnapshot:
    symbol: str
    venue: str
    timestamp_ns: int
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]


@dataclass(slots=True)
class ExecutionFill:
    fill_id: str
    order_id: str
    matched_order_id: str
    price: float
    quantity: float
    taker_side: Side
    venue: str
    latency_ns: int
    fee_paid: float


@dataclass(slots=True)
class ArbitrageVenue:
    venue_id: str
    fee_taker_bps: float
    fee_maker_bps: float
    latency_us: float


@dataclass(slots=True)
class ExchangeLiquidityPool:
    venue_id: str
    base_asset: str
    quote_asset: str
    bid_price: float
    ask_price: float
    bid_depth: float
    ask_depth: float
    slippage_factor: float = 0.00005


@dataclass(slots=True)
class ArbitrageCycle:
    path: List[str]
    venues: List[str]
    gross_return_ratio: float
    net_return_bps: float
    executable_volume: float
    net_profit_usd: float
    total_latency_us: float
    is_profitable: bool


@dataclass(slots=True)
class ArbitrageReport:
    total_cycles_scanned: int
    profitable_cycles: List[ArbitrageCycle]
    max_profit_usd: float
    execution_time_ms: float


@dataclass(slots=True)
class LiquidationParameters:
    initial_shares: float
    time_horizon_sec: float
    intervals: int
    volatility: float
    bid_ask_spread: float
    temporary_impact_eta: float
    permanent_impact_gamma: float
    risk_aversion_lambda: float


@dataclass(slots=True)
class LiquidationStep:
    step: int
    time_sec: float
    remaining_shares: float
    trade_size: float
    trade_rate: float
    expected_price: float
    expected_cost: float
    variance: float


@dataclass(slots=True)
class LiquidationSchedule:
    strategy_name: str
    steps: List[LiquidationStep]
    total_expected_cost: float
    total_variance: float
    utility: float
    half_life_sec: float


@dataclass(slots=True)
class MatchingEngineMetrics:
    total_orders_processed: int
    total_fills: int
    total_volume_matched: float
    total_cancellations: int
    mean_latency_ns: float
    p99_latency_ns: float
    throughput_orders_per_sec: float


@dataclass(slots=True)
class AvellanedaStoikovState:
    mid_price: float
    inventory: int
    time_remaining_sec: float
    risk_aversion_gamma: float
    volatility_sigma: float
    arrival_intensity_A: float
    price_sensitivity_k: float


@dataclass(slots=True)
class MarketMakerQuote:
    reservation_price: float
    optimal_bid: float
    optimal_ask: float
    bid_spread: float
    ask_spread: float
    total_spread: float
    inventory_penalty: float


@dataclass(slots=True)
class MarketMakingSimulationResult:
    total_quotes_generated: int
    total_trades: int
    final_inventory: int
    inventory_pnl: float
    spread_pnl: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float


@dataclass(slots=True)
class OrderVenueAllocation:
    venue: str
    shares_allocated: float
    venue_vwap: float
    venue_fee_usd: float
    venue_latency_penalty_usd: float
    venue_total_cost_usd: float


@dataclass(slots=True)
class RouterDecision:
    total_shares: float
    side: Side
    benchmark_arrival_price: float
    effective_vwap: float
    total_cost_usd: float
    total_slippage_bps: float
    allocations: List[OrderVenueAllocation]
    execution_time_us: float


@dataclass(slots=True)
class HftBenchmarkReport:
    total_runtime_ms: float
    timestamp: str
    arbitrage_summary: Dict[str, float]
    liquidation_summary: Dict[str, float]
    matching_engine_summary: Dict[str, float]
    quoting_summary: Dict[str, float]
    smart_router_summary: Dict[str, float]
