"""
Unit tests for Smart Order Router Convex Allocation Solver.
"""

import unittest
from hft_microstructure_kernel.core.models import Side
from hft_microstructure_kernel.core.smart_order_router import SmartOrderRouterSolver, VenueLiquidityProfile


class TestSmartOrderRouter(unittest.TestCase):

    def setUp(self):
        self.venues = [
            VenueLiquidityProfile("VENUE_A", best_price=100.0, available_shares=10000, impact_slope=0.0001, fee_bps=1.0, latency_us=10.0),
            VenueLiquidityProfile("VENUE_B", best_price=100.0, available_shares=10000, impact_slope=0.0001, fee_bps=1.0, latency_us=10.0),
            VenueLiquidityProfile("VENUE_C", best_price=105.0, available_shares=10000, impact_slope=0.0005, fee_bps=5.0, latency_us=50.0),
        ]
        self.sor = SmartOrderRouterSolver(self.venues)

    def test_symmetric_venues_equal_split(self):
        # A buy of 4,000 shares across symmetric VENUE_A and VENUE_B should allocate equally
        decision = self.sor.route_order(total_shares=4000, side=Side.BUY)
        self.assertEqual(decision.total_shares, 4000)

        # Total allocated shares must sum to 4000
        total_allocated = sum(a.shares_allocated for a in decision.allocations)
        self.assertAlmostEqual(total_allocated, 4000.0, places=3)

        alloc_dict = {a.venue: a.shares_allocated for a in decision.allocations}
        self.assertAlmostEqual(alloc_dict["VENUE_A"], alloc_dict["VENUE_B"], delta=10.0)
        # VENUE_C has much higher price and fee, should get near zero or zero
        self.assertLess(alloc_dict.get("VENUE_C", 0.0), 50.0)

    def test_sor_beats_expensive_single_venue(self):
        # Routing through SOR should be cheaper than routing to the expensive VENUE_C
        decision = self.sor.route_order(total_shares=10000, side=Side.BUY)
        _, _, _, expensive_cost = self.sor.total_cost(self.venues[2], 10000, Side.BUY)
        self.assertLess(decision.total_cost_usd, expensive_cost)


if __name__ == "__main__":
    unittest.main()
