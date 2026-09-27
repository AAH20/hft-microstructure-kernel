"""
Smart Order Router (SOR) Solver for Multi-Venue Liquidity Aggregation.
Formulated as a Non-Linear Convex Resource Allocation Optimization Problem.
Minimizes composite slippage, venue taker fees, and latency adverse selection across venues.
"""

from __future__ import annotations
import math
import time
from typing import List, Dict
from hft_microstructure_kernel.core.models import (
    Side,
    OrderVenueAllocation,
    RouterDecision,
)


class VenueLiquidityProfile:
    """Venue execution profile with order book depth and cost functions."""
    __slots__ = ("venue_id", "best_price", "available_shares", "impact_slope", "fee_bps", "latency_us")

    def __init__(
        self,
        venue_id: str,
        best_price: float,
        available_shares: float,
        impact_slope: float,  # Linear price impact per share: dp = impact_slope * v
        fee_bps: float,       # Taker fee in basis points
        latency_us: float,    # Network round-trip latency in microseconds
    ):
        self.venue_id = venue_id
        self.best_price = best_price
        self.available_shares = available_shares
        self.impact_slope = impact_slope
        self.fee_bps = fee_bps
        self.latency_us = latency_us


class SmartOrderRouterSolver:
    """
    Solves optimal child order allocation across fragmented liquidity venues.
    Implements Karush-Kuhn-Tucker (KKT) marginal cost equalization:
    MC_i(v_i) = P_i + 2 * impact_slope_i * v_i + Fee_i + LatencyPenalty_i = nu
    """

    def __init__(
        self,
        venues: List[VenueLiquidityProfile],
        latency_penalty_per_us: float = 0.00001,  # Dollars per share per microsecond
    ):
        self.venues = venues
        self.latency_penalty_per_us = latency_penalty_per_us

    def marginal_cost(self, venue: VenueLiquidityProfile, v: float, side: Side) -> float:
        """Computes marginal execution cost for allocating volume v to venue."""
        fee_per_share = venue.best_price * (venue.fee_bps / 10000.0)
        lat_cost = venue.latency_us * self.latency_penalty_per_us
        if side == Side.BUY:
            return venue.best_price + (2.0 * venue.impact_slope * v) + fee_per_share + lat_cost
        else:
            return venue.best_price - (2.0 * venue.impact_slope * v) - fee_per_share - lat_cost

    def total_cost(self, venue: VenueLiquidityProfile, v: float, side: Side) -> Tuple[float, float, float, float]:
        """
        Returns (vwap, fee_usd, latency_penalty_usd, total_cost_usd) for allocating volume v.
        Average price = best_price +/- impact_slope * v
        """
        if v <= 0:
            return venue.best_price, 0.0, 0.0, 0.0

        if side == Side.BUY:
            avg_price = venue.best_price + (venue.impact_slope * v)
        else:
            avg_price = venue.best_price - (venue.impact_slope * v)

        notional = avg_price * v
        fee_usd = notional * (venue.fee_bps / 10000.0)
        lat_usd = v * venue.latency_us * self.latency_penalty_per_us
        total_usd = notional + fee_usd + lat_usd if side == Side.BUY else notional - fee_usd - lat_usd

        return avg_price, fee_usd, lat_usd, total_usd

    def route_order(self, total_shares: float, side: Side = Side.BUY) -> RouterDecision:
        """
        Solves optimal allocation v_1, ..., v_M minimizing total execution cost.
        Uses bisection search on the dual shadow price (Lagrange multiplier nu).
        """
        start_time = time.perf_counter()

        if total_shares <= 0 or not self.venues:
            return RouterDecision(
                total_shares=total_shares,
                side=side,
                benchmark_arrival_price=0.0,
                effective_vwap=0.0,
                total_cost_usd=0.0,
                total_slippage_bps=0.0,
                allocations=[],
                execution_time_us=0.0,
            )

        # Baseline arrival price (unweighted average of best venue prices)
        arrival_price = sum(v.best_price for v in self.venues) / len(self.venues)

        # Bounds on marginal cost nu
        # For BUY: higher volume -> higher marginal cost
        # For SELL: higher volume -> lower marginal price received
        if side == Side.BUY:
            nu_min = min(self.marginal_cost(v, 0.0, side) for v in self.venues)
            nu_max = max(self.marginal_cost(v, total_shares, side) for v in self.venues) * 2.0

            # Bisection search for nu such that sum(v_i(nu)) == total_shares
            for _ in range(50):
                nu_mid = (nu_min + nu_max) / 2.0
                total_alloc = 0.0
                for v in self.venues:
                    mc_0 = self.marginal_cost(v, 0.0, side)
                    if nu_mid > mc_0:
                        # v_i = (nu - mc_0) / (2 * impact_slope)
                        allocated = (nu_mid - mc_0) / (2.0 * max(1e-9, v.impact_slope))
                        total_alloc += min(allocated, v.available_shares)

                if total_alloc < total_shares:
                    nu_min = nu_mid
                else:
                    nu_max = nu_mid

            target_nu = (nu_min + nu_max) / 2.0
        else:
            nu_max = max(self.marginal_cost(v, 0.0, side) for v in self.venues)
            nu_min = min(self.marginal_cost(v, total_shares, side) for v in self.venues) * 0.5

            for _ in range(50):
                nu_mid = (nu_min + nu_max) / 2.0
                total_alloc = 0.0
                for v in self.venues:
                    mc_0 = self.marginal_cost(v, 0.0, side)
                    if nu_mid < mc_0:
                        allocated = (mc_0 - nu_mid) / (2.0 * max(1e-9, v.impact_slope))
                        total_alloc += min(allocated, v.available_shares)

                if total_alloc < total_shares:
                    nu_max = nu_mid
                else:
                    nu_min = nu_mid

            target_nu = (nu_min + nu_max) / 2.0

        # Construct optimal allocations
        allocations: List[OrderVenueAllocation] = []
        shares_routed = 0.0
        total_spent_usd = 0.0

        for v in self.venues:
            mc_0 = self.marginal_cost(v, 0.0, side)
            if side == Side.BUY:
                if target_nu > mc_0:
                    alloc_shares = min(
                        (target_nu - mc_0) / (2.0 * max(1e-9, v.impact_slope)),
                        v.available_shares,
                        total_shares - shares_routed,
                    )
                else:
                    alloc_shares = 0.0
            else:
                if target_nu < mc_0:
                    alloc_shares = min(
                        (mc_0 - target_nu) / (2.0 * max(1e-9, v.impact_slope)),
                        v.available_shares,
                        total_shares - shares_routed,
                    )
                else:
                    alloc_shares = 0.0

            if alloc_shares > 1e-4:
                vwap, fee, lat, total_ven_cost = self.total_cost(v, alloc_shares, side)
                allocations.append(OrderVenueAllocation(
                    venue=v.venue_id,
                    shares_allocated=alloc_shares,
                    venue_vwap=vwap,
                    venue_fee_usd=fee,
                    venue_latency_penalty_usd=lat,
                    venue_total_cost_usd=total_ven_cost,
                ))
                shares_routed += alloc_shares
                total_spent_usd += total_ven_cost

        # If any shares remain unallocated due to capacity bounds, distribute to venue with lowest marginal impact
        residual = total_shares - shares_routed
        if residual > 1e-4 and self.venues:
            best_v = min(self.venues, key=lambda v: v.impact_slope)
            # Find if best_v is in allocations
            alloc_entry = next((a for a in allocations if a.venue == best_v.venue_id), None)
            if alloc_entry:
                new_shares = alloc_entry.shares_allocated + residual
                vwap, fee, lat, total_ven_cost = self.total_cost(best_v, new_shares, side)
                total_spent_usd += (total_ven_cost - alloc_entry.venue_total_cost_usd)
                alloc_entry.shares_allocated = new_shares
                alloc_entry.venue_vwap = vwap
                alloc_entry.venue_fee_usd = fee
                alloc_entry.venue_latency_penalty_usd = lat
                alloc_entry.venue_total_cost_usd = total_ven_cost
            else:
                vwap, fee, lat, total_ven_cost = self.total_cost(best_v, residual, side)
                allocations.append(OrderVenueAllocation(
                    venue=best_v.venue_id,
                    shares_allocated=residual,
                    venue_vwap=vwap,
                    venue_fee_usd=fee,
                    venue_latency_penalty_usd=lat,
                    venue_total_cost_usd=total_ven_cost,
                ))
                total_spent_usd += total_ven_cost
            shares_routed += residual

        effective_vwap = (total_spent_usd / total_shares) if total_shares > 0 else arrival_price
        slippage_bps = abs(effective_vwap - arrival_price) / arrival_price * 10000.0

        elapsed_us = (time.perf_counter() - start_time) * 1_000_000.0

        return RouterDecision(
            total_shares=total_shares,
            side=side,
            benchmark_arrival_price=arrival_price,
            effective_vwap=effective_vwap,
            total_cost_usd=total_spent_usd,
            total_slippage_bps=slippage_bps,
            allocations=allocations,
            execution_time_us=elapsed_us,
        )
