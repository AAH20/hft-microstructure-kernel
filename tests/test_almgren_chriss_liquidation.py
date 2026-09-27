"""
Unit tests for Almgren-Chriss Optimal Liquidation Solver.
"""

import unittest
from hft_microstructure_kernel.core.models import LiquidationParameters
from hft_microstructure_kernel.core.almgren_chriss_liquidation import AlmgrenChrissSolver


class TestAlmgrenChrissLiquidation(unittest.TestCase):

    def setUp(self):
        self.params = LiquidationParameters(
            initial_shares=500_000.0,
            time_horizon_sec=1800.0,
            intervals=30,
            volatility=0.015,
            bid_ask_spread=0.04,
            temporary_impact_eta=3.0e-6,
            permanent_impact_gamma=3.0e-7,
            risk_aversion_lambda=2.0e-5,
        )
        self.solver = AlmgrenChrissSolver(self.params)

    def test_optimal_schedule_exhausts_inventory(self):
        sched = self.solver.compute_optimal_schedule()
        self.assertEqual(len(sched.steps), self.params.intervals)
        # Final remaining shares should be exactly 0
        self.assertAlmostEqual(sched.steps[-1].remaining_shares, 0.0, places=5)
        # Sum of trade sizes must equal initial shares
        total_traded = sum(s.trade_size for s in sched.steps)
        self.assertAlmostEqual(total_traded, self.params.initial_shares, places=3)

    def test_risk_averse_has_lower_variance_than_twap(self):
        optimal_sched = self.solver.compute_optimal_schedule()
        twap_sched = self.solver.compute_twap_schedule()

        # Risk-averse strategy must achieve strictly lower variance than linear TWAP
        self.assertLess(optimal_sched.total_variance, twap_sched.total_variance)
        # Optimal schedule must minimize utility = E[x] + lambda * Var[x]
        self.assertLessEqual(optimal_sched.utility, twap_sched.utility)

    def test_zero_risk_aversion_approaches_twap(self):
        neutral_params = LiquidationParameters(
            initial_shares=100_000.0,
            time_horizon_sec=600.0,
            intervals=10,
            volatility=0.01,
            bid_ask_spread=0.02,
            temporary_impact_eta=1e-6,
            permanent_impact_gamma=1e-7,
            risk_aversion_lambda=0.0,  # Pure risk-neutral
        )
        neutral_solver = AlmgrenChrissSolver(neutral_params)
        opt = neutral_solver.compute_optimal_schedule()
        twap = neutral_solver.compute_twap_schedule()

        self.assertAlmostEqual(opt.total_expected_cost, twap.total_expected_cost, places=3)


if __name__ == "__main__":
    unittest.main()
