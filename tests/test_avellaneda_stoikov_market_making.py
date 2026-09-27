"""
Unit tests for Avellaneda-Stoikov Market Making Solver.
"""

import unittest
from hft_microstructure_kernel.core.models import AvellanedaStoikovState
from hft_microstructure_kernel.core.avellaneda_stoikov_market_making import AvellanedaStoikovSolver


class TestAvellanedaStoikovMarketMaking(unittest.TestCase):

    def test_reservation_price_inventory_asymmetry(self):
        # Neutral inventory q = 0
        state_neutral = AvellanedaStoikovState(
            mid_price=100.0,
            inventory=0,
            time_remaining_sec=10.0,
            risk_aversion_gamma=0.1,
            volatility_sigma=0.5,
            arrival_intensity_A=100.0,
            price_sensitivity_k=1.5,
        )
        quote_neutral = AvellanedaStoikovSolver.compute_quote(state_neutral)
        self.assertEqual(quote_neutral.reservation_price, 100.0)
        self.assertAlmostEqual(quote_neutral.bid_spread, quote_neutral.ask_spread, places=5)

        # Long inventory q = +10 -> Reservation price must drop below mid-price
        state_long = AvellanedaStoikovState(
            mid_price=100.0,
            inventory=10,
            time_remaining_sec=10.0,
            risk_aversion_gamma=0.1,
            volatility_sigma=0.5,
            arrival_intensity_A=100.0,
            price_sensitivity_k=1.5,
        )
        quote_long = AvellanedaStoikovSolver.compute_quote(state_long)
        self.assertLess(quote_long.reservation_price, 100.0)
        # Bid spread should be wider (less eager to buy), Ask spread tighter (more eager to sell)
        self.assertGreater(quote_long.bid_spread, quote_long.ask_spread)

        # Short inventory q = -10 -> Reservation price must rise above mid-price
        state_short = AvellanedaStoikovState(
            mid_price=100.0,
            inventory=-10,
            time_remaining_sec=10.0,
            risk_aversion_gamma=0.1,
            volatility_sigma=0.5,
            arrival_intensity_A=100.0,
            price_sensitivity_k=1.5,
        )
        quote_short = AvellanedaStoikovSolver.compute_quote(state_short)
        self.assertGreater(quote_short.reservation_price, 100.0)
        self.assertLess(quote_short.bid_spread, quote_short.ask_spread)

    def test_session_simulation_execution(self):
        solver = AvellanedaStoikovSolver()
        result, quotes = solver.simulate_session(
            initial_price=100.0,
            total_time_sec=10.0,
            dt=0.1,
            seed=123,
        )
        self.assertEqual(len(quotes), 100)
        self.assertGreater(result.total_trades, 0)
        self.assertIsInstance(result.total_pnl, float)


if __name__ == "__main__":
    unittest.main()
