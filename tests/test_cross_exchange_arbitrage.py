"""
Unit tests for Cross-Exchange & Triangular Arbitrage Solver.
"""

import unittest
from hft_microstructure_kernel.core.models import (
    ArbitrageVenue,
    ExchangeLiquidityPool,
)
from hft_microstructure_kernel.core.cross_exchange_arbitrage import CrossExchangeArbitrageSolver


class TestCrossExchangeArbitrage(unittest.TestCase):

    def setUp(self):
        self.venues = {
            "VENUE_A": ArbitrageVenue("VENUE_A", fee_taker_bps=2.0, fee_maker_bps=-0.5, latency_us=10.0),
            "VENUE_B": ArbitrageVenue("VENUE_B", fee_taker_bps=2.0, fee_maker_bps=0.0, latency_us=15.0),
            "VENUE_C": ArbitrageVenue("VENUE_C", fee_taker_bps=2.0, fee_maker_bps=0.0, latency_us=20.0),
        }

    def test_profitable_triangular_cycle(self):
        # Create an artificial triangular arbitrage: USD -> EUR -> GBP -> USD
        # USD -> EUR at 0.92 (1 USD = 0.92 EUR)
        # EUR -> GBP at 0.88 (1 EUR = 0.88 GBP -> 0.92 * 0.88 = 0.8096 GBP)
        # GBP -> USD at 1.30 (1 GBP = 1.30 USD -> 0.8096 * 1.30 = 1.05248 USD -> +5.2% gross edge)
        pools = [
            ExchangeLiquidityPool("VENUE_A", "EUR", "USD", bid_price=1.087, ask_price=1.087, bid_depth=100000.0, ask_depth=100000.0, slippage_factor=0.0001),
            ExchangeLiquidityPool("VENUE_B", "GBP", "EUR", bid_price=1.136, ask_price=1.136, bid_depth=100000.0, ask_depth=100000.0, slippage_factor=0.0001),
            ExchangeLiquidityPool("VENUE_C", "GBP", "USD", bid_price=1.300, ask_price=1.300, bid_depth=100000.0, ask_depth=100000.0, slippage_factor=0.0001),
        ]
        solver = CrossExchangeArbitrageSolver(self.venues, pools)
        report = solver.find_arbitrage_cycles(base_currency="USD", max_hops=3)

        self.assertGreater(report.total_cycles_scanned, 0)
        self.assertGreater(len(report.profitable_cycles), 0)
        best = report.profitable_cycles[0]
        self.assertTrue(best.is_profitable)
        self.assertGreater(best.net_profit_usd, 0.0)
        self.assertGreater(best.executable_volume, 0.0)

    def test_no_arbitrage_market(self):
        # Perfectly consistent exchange rates (no arb)
        pools = [
            ExchangeLiquidityPool("VENUE_A", "BTC", "USD", bid_price=60000.0, ask_price=60005.0, bid_depth=10.0, ask_depth=10.0),
            ExchangeLiquidityPool("VENUE_B", "BTC", "USD", bid_price=59995.0, ask_price=60000.0, bid_depth=10.0, ask_depth=10.0),
        ]
        solver = CrossExchangeArbitrageSolver(self.venues, pools)
        report = solver.find_arbitrage_cycles(base_currency="USD", max_hops=3)
        self.assertEqual(len(report.profitable_cycles), 0)
        self.assertEqual(report.max_profit_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
