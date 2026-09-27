"""
Unit tests for Deterministic High-Frequency Matching Engine.
"""

import unittest
from hft_microstructure_kernel.core.models import (
    Side,
    LimitOrder,
)
from hft_microstructure_kernel.core.lock_free_matching_engine import HighFrequencyMatchingEngine


class TestLockFreeMatchingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = HighFrequencyMatchingEngine(symbol="ETH-USD", venue="TEST_VENUE")

    def test_limit_order_insertion_and_depth(self):
        # Insert bids
        self.engine.submit_order(LimitOrder("b1", "ETH-USD", Side.BUY, 3000.0, 5.0, 100))
        self.engine.submit_order(LimitOrder("b2", "ETH-USD", Side.BUY, 3005.0, 2.0, 101))
        # Insert asks
        self.engine.submit_order(LimitOrder("a1", "ETH-USD", Side.SELL, 3010.0, 4.0, 102))
        self.engine.submit_order(LimitOrder("a2", "ETH-USD", Side.SELL, 3015.0, 3.0, 103))

        self.assertEqual(self.engine.best_bid, 3005.0)
        self.assertEqual(self.engine.best_ask, 3010.0)
        self.assertEqual(self.engine.mid_price, 3007.5)

        snap = self.engine.get_snapshot(depth=5)
        self.assertEqual(len(snap.bids), 2)
        self.assertEqual(len(snap.asks), 2)
        self.assertEqual(snap.bids[0].price, 3005.0)
        self.assertEqual(snap.bids[0].quantity, 2.0)

    def test_order_matching_execution(self):
        # Place resting ask
        self.engine.submit_order(LimitOrder("a1", "ETH-USD", Side.SELL, 3000.0, 10.0, 100))
        # Place crossing buy
        fills = self.engine.submit_order(LimitOrder("b1", "ETH-USD", Side.BUY, 3005.0, 4.0, 105))

        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.price, 3000.0)  # Matches at resting maker price
        self.assertEqual(fill.quantity, 4.0)
        self.assertEqual(fill.matched_order_id, "a1")

        # Check remaining resting quantity on ask
        snap = self.engine.get_snapshot(depth=5)
        self.assertEqual(snap.asks[0].quantity, 6.0)

    def test_order_cancellation(self):
        self.engine.submit_order(LimitOrder("b1", "ETH-USD", Side.BUY, 2990.0, 10.0, 100))
        self.assertEqual(self.engine.best_bid, 2990.0)

        # Cancel order
        success = self.engine.cancel_order("b1")
        self.assertTrue(success)
        self.assertIsNone(self.engine.best_bid)

        # Cancelling non-existent order should return False
        self.assertFalse(self.engine.cancel_order("non_existent"))


if __name__ == "__main__":
    unittest.main()
