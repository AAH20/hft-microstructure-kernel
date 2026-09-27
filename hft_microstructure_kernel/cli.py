"""
Command-Line Interface for Quantitative HFT & Market Microstructure Kernel.
Provides CLI commands for individual solvers and unified benchmark execution.
"""

from __future__ import annotations
import argparse
import json
import sys
from hft_microstructure_kernel.engine import HftMicrostructureEngine


def print_banner():
    banner = r"""
================================================================================
   QUANTITATIVE HIGH-FREQUENCY TRADING & MARKET MICROSTRUCTURE KERNEL
   Zero-Dependency Microsecond Algorithmic Execution & Microstructure Suite
================================================================================
"""
    print(banner)


def run_benchmark_all():
    print_banner()
    print("[*] Initializing Quantitative Microstructure Benchmarks...")
    engine = HftMicrostructureEngine()

    report = engine.run_comprehensive_benchmark()

    print("\n" + "=" * 80)
    print("1. CROSS-EXCHANGE ARBITRAGE SOLVER (NEGATIVE CYCLE & DEPTH SLIPPAGE)")
    print("=" * 80)
    arb = report.arbitrage_summary
    print(f"  * Total Directed Cycles Scanned  : {arb['total_cycles_scanned']}")
    print(f"  * Profitable Arbitrage Paths     : {arb['profitable_cycles_found']}")
    print(f"  * Best Arbitrage Route           : {arb['best_cycle_path']}")
    print(f"  * Best Route Net Edge            : {arb['best_cycle_net_bps']:.2f} bps")
    print(f"  * Max Risk-Adjusted Profit       : ${arb['max_profit_usd']:,.2f}")
    print(f"  * Graph Solver Execution Time    : {arb['solver_latency_ms']:.3f} ms")

    print("\n" + "=" * 80)
    print("2. ALMGREN-CHRISS OPTIMAL LIQUIDATION (EULER-LAGRANGE HYPERBOLIC)")
    print("=" * 80)
    liq = report.liquidation_summary
    print(f"  * Initial Portfolio Size         : {liq['initial_shares']:,.0f} shares ($100M notional)")
    print(f"  * Execution Time Horizon         : {liq['time_horizon_sec']}s (1.0 hour)")
    print(f"  * Optimal Shortfall Cost         : ${liq['optimal_expected_cost']:,.2f}")
    print(f"  * Baseline Linear TWAP Cost      : ${liq['twap_expected_cost']:,.2f}")
    print(f"  * Risk-Adjusted Utility Savings  : ${liq['utility_savings_usd']:,.2f}")
    print(f"  * Volatility Variance Reduction  : {liq['variance_reduction_pct']:.2f}%")
    print(f"  * Trajectory Half-Life           : {liq['half_life_sec']:.1f}s")

    print("\n" + "=" * 80)
    print("3. DETERMINISTIC FIFO MATCHING ENGINE (MICROSECOND LOB)")
    print("=" * 80)
    match = report.matching_engine_summary
    print(f"  * Total Orders Processed         : {match['total_orders_processed']:,}")
    print(f"  * Executed Fills Generated       : {match['total_fills']:,}")
    print(f"  * Total Traded Volume            : {match['total_volume_matched']:,.2f} BTC")
    print(f"  * Order Cancellations Serviced   : {match['total_cancellations']:,}")
    print(f"  * Mean Order Matching Latency    : {match['mean_latency_ns']:.1f} ns ({match['mean_latency_ns']/1000.0:.2f} µs)")
    print(f"  * p99 Tail Matching Latency      : {match['p99_latency_ns']:.1f} ns ({match['p99_latency_ns']/1000.0:.2f} µs)")
    print(f"  * Peak Sustained Throughput      : {match['throughput_orders_per_sec']:,.0f} orders/sec")

    print("\n" + "=" * 80)
    print("4. AVELLANEDA-STOIKOV MARKET MAKING (POISSON ORDER ARRIVALS)")
    print("=" * 80)
    quote = report.quoting_summary
    print(f"  * Quotes Dynamic Updates         : {quote['total_quotes_generated']:,}")
    print(f"  * Two-Sided Trades Executed      : {quote['total_trades_filled']:,}")
    print(f"  * Ending Inventory               : {quote['final_inventory_units']} units (inventory neutral)")
    print(f"  * Realized Half-Spread Profit    : ${quote['realized_spread_pnl']:,.2f}")
    print(f"  * Total Trading Session PnL      : ${quote['total_pnl_usd']:,.2f}")
    print(f"  * Annualized Sharpe Ratio        : {quote['sharpe_ratio']:.2f}")
    print(f"  * Max Strategy Drawdown          : ${quote['max_drawdown_usd']:.2f}")

    print("\n" + "=" * 80)
    print("5. SMART ORDER ROUTER (CONVEX RESOURCE ALLOCATION / KKT EQUALIZATION)")
    print("=" * 80)
    sor = report.smart_router_summary
    print(f"  * Parent Order Notional Volume   : {sor['total_shares']:,} shares")
    print(f"  * Unweighted Arrival Price       : ${sor['arrival_price']:.4f}")
    print(f"  * Effective Realized VWAP        : ${sor['effective_vwap']:.4f}")
    print(f"  * Total Slippage Impact          : {sor['total_slippage_bps']:.2f} bps")
    print(f"  * Liquidity Venues Dispatched    : {sor['active_venues_routed']} exchanges & dark pools")
    print(f"  * Single-Venue Naive Cost        : ${sor['single_venue_cme_cost']:,.2f}")
    print(f"  * SOR Convex Optimized Cost      : ${sor['sor_optimized_cost']:,.2f}")
    print(f"  * SOR Total Cost Savings         : ${sor['cost_savings_usd']:,.2f} ({sor['cost_savings_bps']:.1f} bps)")
    print(f"  * Multi-Venue Routing Latency    : {sor['routing_latency_us']:.2f} µs")

    print("\n" + "=" * 80)
    print(f"ALL 5 QUANTITATIVE SOLVERS EXECUTED IN {report.total_runtime_ms:.2f} ms")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Quantitative High-Frequency Trading & Market Microstructure Benchmark CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("benchmark-all", help="Execute all 5 quantitative solvers with complete telemetry")
    subparsers.add_parser("arbitrage", help="Run Cross-Exchange Negative Cycle Arbitrage solver")
    subparsers.add_parser("liquidation", help="Run Almgren-Chriss Optimal Liquidation solver")
    subparsers.add_parser("matching", help="Run High-Frequency LOB Matching Engine benchmark")
    subparsers.add_parser("quoting", help="Run Avellaneda-Stoikov Market Maker simulation")
    subparsers.add_parser("routing", help="Run Smart Order Router Convex Allocation solver")

    args = parser.parse_args()

    engine = HftMicrostructureEngine()

    if args.command == "benchmark-all" or args.command is None:
        run_benchmark_all()
    elif args.command == "arbitrage":
        res = engine.run_arbitrage_benchmark()
        print(json.dumps(res, indent=2))
    elif args.command == "liquidation":
        res = engine.run_liquidation_benchmark()
        print(json.dumps(res, indent=2))
    elif args.command == "matching":
        res = engine.run_matching_benchmark()
        print(json.dumps(res, indent=2))
    elif args.command == "quoting":
        res = engine.run_quoting_benchmark()
        print(json.dumps(res, indent=2))
    elif args.command == "routing":
        res = engine.run_router_benchmark()
        print(json.dumps(res, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
