"""
Unit tests for integrated HftMicrostructureEngine.
"""

import unittest
from hft_microstructure_kernel.engine import HftMicrostructureEngine


class TestHftMicrostructureEngine(unittest.TestCase):

    def setUp(self):
        self.engine = HftMicrostructureEngine()

    def test_run_arbitrage_benchmark(self):
        res = self.engine.run_arbitrage_benchmark()
        self.assertIn("total_cycles_scanned", res)
        self.assertIn("profitable_cycles_found", res)
        self.assertGreater(res["total_cycles_scanned"], 0)

    def test_run_liquidation_benchmark(self):
        res = self.engine.run_liquidation_benchmark()
        self.assertIn("optimal_expected_cost", res)
        self.assertIn("twap_expected_cost", res)
        self.assertGreater(res["utility_savings_usd"], 0.0)
        self.assertGreater(res["variance_reduction_pct"], 90.0)

    def test_run_matching_benchmark(self):
        res = self.engine.run_matching_benchmark(num_orders=500)
        self.assertIn("total_orders_processed", res)
        self.assertGreater(res["throughput_orders_per_sec"], 1000.0)

    def test_run_quoting_benchmark(self):
        res = self.engine.run_quoting_benchmark()
        self.assertIn("total_quotes_generated", res)
        self.assertGreater(res["total_quotes_generated"], 0)

    def test_run_router_benchmark(self):
        res = self.engine.run_router_benchmark()
        self.assertIn("effective_vwap", res)
        self.assertGreater(res["cost_savings_usd"], 0.0)

    def test_run_comprehensive_benchmark(self):
        report = self.engine.run_comprehensive_benchmark()
        self.assertGreater(report.total_runtime_ms, 0.0)
        self.assertIsNotNone(report.arbitrage_summary)
        self.assertIsNotNone(report.liquidation_summary)
        self.assertIsNotNone(report.matching_engine_summary)
        self.assertIsNotNone(report.quoting_summary)
        self.assertIsNotNone(report.smart_router_summary)


if __name__ == "__main__":
    unittest.main()
