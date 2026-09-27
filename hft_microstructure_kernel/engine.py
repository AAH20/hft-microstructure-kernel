"""
Execution engine orchestrating all 5 HFT & market microstructure solvers into
an integrated benchmark pipeline with sub-millisecond telemetry.
"""

from __future__ import annotations
import datetime
import time
from typing import Dict, Any, List
from hft_microstructure_kernel.core.models import (
    Side,
    OrderType,
    LimitOrder,
    ArbitrageVenue,
    ExchangeLiquidityPool,
    LiquidationParameters,
    AvellanedaStoikovState,
    HftBenchmarkReport,
)
from hft_microstructure_kernel.core.cross_exchange_arbitrage import CrossExchangeArbitrageSolver
from hft_microstructure_kernel.core.almgren_chriss_liquidation import AlmgrenChrissSolver
from hft_microstructure_kernel.core.lock_free_matching_engine import HighFrequencyMatchingEngine
from hft_microstructure_kernel.core.avellaneda_stoikov_market_making import AvellanedaStoikovSolver
from hft_microstructure_kernel.core.smart_order_router import SmartOrderRouterSolver, VenueLiquidityProfile


class HftMicrostructureEngine:
    """Orchestrates comprehensive microsecond-grade algorithmic benchmarks."""

    def __init__(self):
        pass

    def run_arbitrage_benchmark(self) -> Dict[str, Any]:
        """Runs multi-venue triangular & polygon negative-cycle arbitrage detection."""
        venues = {
            "CME": ArbitrageVenue("CME", fee_taker_bps=2.0, fee_maker_bps=-0.5, latency_us=12.0),
            "BINANCE": ArbitrageVenue("BINANCE", fee_taker_bps=4.0, fee_maker_bps=1.0, latency_us=35.0),
            "COINBASE": ArbitrageVenue("COINBASE", fee_taker_bps=5.0, fee_maker_bps=2.0, latency_us=40.0),
            "KRAKEN": ArbitrageVenue("KRAKEN", fee_taker_bps=6.0, fee_maker_bps=2.5, latency_us=45.0),
        }

        # Multi-currency liquidity pools across venues
        pools = [
            # CME: BTC/USD
            ExchangeLiquidityPool("CME", "BTC", "USD", bid_price=64250.0, ask_price=64255.0, bid_depth=85.0, ask_depth=90.0),
            # BINANCE: BTC/EUR
            ExchangeLiquidityPool("BINANCE", "BTC", "EUR", bid_price=59500.0, ask_price=59505.0, bid_depth=120.0, ask_depth=110.0),
            # COINBASE: EUR/USD
            ExchangeLiquidityPool("COINBASE", "EUR", "USD", bid_price=1.0825, ask_price=1.0828, bid_depth=5000000.0, ask_depth=5000000.0),
            # KRAKEN: BTC/USD
            ExchangeLiquidityPool("KRAKEN", "BTC", "USD", bid_price=64260.0, ask_price=64265.0, bid_depth=65.0, ask_depth=70.0),
            # KRAKEN: ETH/USD
            ExchangeLiquidityPool("KRAKEN", "ETH", "USD", bid_price=3450.0, ask_price=3452.0, bid_depth=500.0, ask_depth=450.0),
            # BINANCE: ETH/BTC
            ExchangeLiquidityPool("BINANCE", "ETH", "BTC", bid_price=0.05372, ask_price=0.05374, bid_depth=400.0, ask_depth=380.0),
        ]

        solver = CrossExchangeArbitrageSolver(venues, pools)
        report = solver.find_arbitrage_cycles(base_currency="USD", max_hops=4)

        return {
            "total_cycles_scanned": report.total_cycles_scanned,
            "profitable_cycles_found": len(report.profitable_cycles),
            "max_profit_usd": report.max_profit_usd,
            "best_cycle_path": " -> ".join(report.profitable_cycles[0].path) if report.profitable_cycles else "None",
            "best_cycle_net_bps": report.profitable_cycles[0].net_return_bps if report.profitable_cycles else 0.0,
            "solver_latency_ms": report.execution_time_ms,
        }

    def run_liquidation_benchmark(self) -> Dict[str, Any]:
        """Runs Almgren-Chriss optimal liquidation vs linear TWAP baseline."""
        # 1,000,000 shares liquidation over 1 hour (3600 seconds, 60 intervals)
        params = LiquidationParameters(
            initial_shares=1_000_000.0,
            time_horizon_sec=3600.0,
            intervals=60,
            volatility=0.02,              # Daily vol ~ 2%
            bid_ask_spread=0.05,          # $0.05 spread
            temporary_impact_eta=2.5e-6,  # Temporary price impact factor
            permanent_impact_gamma=2.5e-7,# Permanent price impact factor
            risk_aversion_lambda=1e-5,    # Institutional risk aversion
        )

        solver = AlmgrenChrissSolver(params)
        optimal_sched = solver.compute_optimal_schedule()
        twap_sched = solver.compute_twap_schedule()

        utility_savings_usd = twap_sched.utility - optimal_sched.utility
        variance_reduction_pct = (twap_sched.total_variance - optimal_sched.total_variance) / twap_sched.total_variance * 100.0

        return {
            "initial_shares": params.initial_shares,
            "time_horizon_sec": params.time_horizon_sec,
            "optimal_expected_cost": optimal_sched.total_expected_cost,
            "twap_expected_cost": twap_sched.total_expected_cost,
            "utility_savings_usd": utility_savings_usd,
            "variance_reduction_pct": variance_reduction_pct,
            "half_life_sec": optimal_sched.half_life_sec,
            "optimal_utility": optimal_sched.utility,
        }

    def run_matching_benchmark(self, num_orders: int = 5000) -> Dict[str, Any]:
        """Runs deterministic high-throughput matching engine benchmark."""
        engine = HighFrequencyMatchingEngine(symbol="BTC-USD", venue="GLOBEX_L3")

        # Pre-seed book with resting limit orders
        for i in range(100):
            engine.submit_order(LimitOrder(
                order_id=f"bid_seed_{i}",
                symbol="BTC-USD",
                side=Side.BUY,
                price=64000.0 - (i * 0.5),
                quantity=1.0 + (i % 5),
                timestamp_ns=time.perf_counter_ns(),
            ))
            engine.submit_order(LimitOrder(
                order_id=f"ask_seed_{i}",
                symbol="BTC-USD",
                side=Side.SELL,
                price=64001.0 + (i * 0.5),
                quantity=1.0 + (i % 5),
                timestamp_ns=time.perf_counter_ns(),
            ))

        # Benchmark high-rate mixed order flow (market orders, aggressive limit orders, cancels)
        start_t = time.perf_counter()
        for i in range(num_orders):
            side = Side.BUY if i % 2 == 0 else Side.SELL
            price = 64001.0 if side == Side.BUY else 64000.0
            order = LimitOrder(
                order_id=f"bench_ord_{i}",
                symbol="BTC-USD",
                side=side,
                price=price,
                quantity=0.5,
                timestamp_ns=time.perf_counter_ns(),
            )
            engine.submit_order(order)

            # 10% cancellations
            if i % 10 == 0 and i > 20:
                engine.cancel_order(f"bid_seed_{i % 50}")

        metrics = engine.get_metrics()
        elapsed_sec = time.perf_counter() - start_t

        return {
            "total_orders_processed": metrics.total_orders_processed,
            "total_fills": metrics.total_fills,
            "total_volume_matched": metrics.total_volume_matched,
            "total_cancellations": metrics.total_cancellations,
            "mean_latency_ns": metrics.mean_latency_ns,
            "p99_latency_ns": metrics.p99_latency_ns,
            "throughput_orders_per_sec": (num_orders + 200) / elapsed_sec if elapsed_sec > 0 else 0.0,
        }

    def run_quoting_benchmark(self) -> Dict[str, Any]:
        """Runs Avellaneda-Stoikov market making stochastic session simulation."""
        solver = AvellanedaStoikovSolver()
        result, quotes = solver.simulate_session(
            initial_price=100.0,
            total_time_sec=60.0,
            dt=0.1,
            gamma=0.1,
            sigma=0.3,
            A=140.0,
            k=1.5,
            seed=42,
        )

        return {
            "total_quotes_generated": result.total_quotes_generated,
            "total_trades_filled": result.total_trades,
            "final_inventory_units": result.final_inventory,
            "realized_spread_pnl": result.spread_pnl,
            "total_pnl_usd": result.total_pnl,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_usd": result.max_drawdown,
        }

    def run_router_benchmark(self) -> Dict[str, Any]:
        """Runs Smart Order Router convex multi-venue allocation."""
        venues = [
            VenueLiquidityProfile("CME", best_price=100.00, available_shares=50000, impact_slope=0.00002, fee_bps=1.5, latency_us=10.0),
            VenueLiquidityProfile("NASDAQ", best_price=100.01, available_shares=40000, impact_slope=0.000025, fee_bps=2.0, latency_us=15.0),
            VenueLiquidityProfile("BATS", best_price=100.02, available_shares=30000, impact_slope=0.00003, fee_bps=1.8, latency_us=25.0),
            VenueLiquidityProfile("IEX", best_price=100.00, available_shares=20000, impact_slope=0.000015, fee_bps=0.9, latency_us=350.0),
            VenueLiquidityProfile("DARK_POOL", best_price=99.98, available_shares=15000, impact_slope=0.00001, fee_bps=1.0, latency_us=50.0),
        ]

        sor = SmartOrderRouterSolver(venues)
        decision = sor.route_order(total_shares=50000, side=Side.BUY)

        # Baseline single venue (e.g., routing 100% to CME)
        _, _, _, cme_only_cost = sor.total_cost(venues[0], 50000, Side.BUY)
        sor_savings_usd = cme_only_cost - decision.total_cost_usd
        sor_savings_bps = (sor_savings_usd / cme_only_cost) * 10000.0 if cme_only_cost > 0 else 0.0

        return {
            "total_shares": decision.total_shares,
            "arrival_price": decision.benchmark_arrival_price,
            "effective_vwap": decision.effective_vwap,
            "total_slippage_bps": decision.total_slippage_bps,
            "active_venues_routed": len(decision.allocations),
            "single_venue_cme_cost": cme_only_cost,
            "sor_optimized_cost": decision.total_cost_usd,
            "cost_savings_usd": sor_savings_usd,
            "cost_savings_bps": sor_savings_bps,
            "routing_latency_us": decision.execution_time_us,
        }

    def run_comprehensive_benchmark(self) -> HftBenchmarkReport:
        """Runs the entire quantitative suite and aggregates telemetry."""
        t0 = time.perf_counter()

        arb_res = self.run_arbitrage_benchmark()
        liq_res = self.run_liquidation_benchmark()
        match_res = self.run_matching_benchmark()
        quote_res = self.run_quoting_benchmark()
        router_res = self.run_router_benchmark()

        total_runtime_ms = (time.perf_counter() - t0) * 1000.0

        return HftBenchmarkReport(
            total_runtime_ms=total_runtime_ms,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            arbitrage_summary=arb_res,
            liquidation_summary=liq_res,
            matching_engine_summary=match_res,
            quoting_summary=quote_res,
            smart_router_summary=router_res,
        )
