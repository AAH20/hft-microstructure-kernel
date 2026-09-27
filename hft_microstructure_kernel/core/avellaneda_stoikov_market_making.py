"""
Avellaneda-Stoikov (2008) High-Frequency Market Making Solver.
Computes optimal reservation prices and dynamic asymmetric bid/ask spreads under
inventory risk aversion and Poisson order arrival intensity.
"""

from __future__ import annotations
import math
import random
from typing import List, Tuple
from hft_microstructure_kernel.core.models import (
    AvellanedaStoikovState,
    MarketMakerQuote,
    MarketMakingSimulationResult,
)


class AvellanedaStoikovSolver:
    """
    Solves the continuous-time Hamilton-Jacobi-Bellman (HJB) equations for an optimal
    high-frequency market maker managing inventory risk and adverse selection.
    """

    @staticmethod
    def compute_quote(state: AvellanedaStoikovState) -> MarketMakerQuote:
        """
        Computes optimal reservation price and bid/ask quotes:
        r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
        delta_spread = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / k)
        """
        s = state.mid_price
        q = state.inventory
        t_rem = max(1e-4, state.time_remaining_sec)
        gamma = state.risk_aversion_gamma
        sigma = state.volatility_sigma
        k = state.price_sensitivity_k

        # Reservation price (indifference price)
        inventory_penalty = q * gamma * (sigma ** 2) * t_rem
        reservation_price = s - inventory_penalty

        # Spread component from liquidity liquidity parameter k
        spread_half = (1.0 / gamma) * math.log(1.0 + (gamma / k))

        optimal_bid = reservation_price - spread_half
        optimal_ask = reservation_price + spread_half

        bid_spread = s - optimal_bid
        ask_spread = optimal_ask - s
        total_spread = optimal_ask - optimal_bid

        return MarketMakerQuote(
            reservation_price=reservation_price,
            optimal_bid=optimal_bid,
            optimal_ask=optimal_ask,
            bid_spread=bid_spread,
            ask_spread=ask_spread,
            total_spread=total_spread,
            inventory_penalty=inventory_penalty,
        )

    def simulate_session(
        self,
        initial_price: float = 100.0,
        total_time_sec: float = 60.0,
        dt: float = 0.1,
        gamma: float = 0.1,
        sigma: float = 0.3,
        A: float = 140.0,
        k: float = 1.5,
        seed: int = 42,
    ) -> Tuple[MarketMakingSimulationResult, List[MarketMakerQuote]]:
        """
        Simulates a full market making trading session over [0, T] using discrete Poisson steps.
        Evaluates cumulative PnL, inventory variance, and execution Sharpe ratio.
        """
        prng = random.Random(seed)
        steps = int(total_time_sec / dt)
        current_price = initial_price
        q = 0
        cash = 0.0
        trades_executed = 0
        quotes: List[MarketMakerQuote] = []
        pnl_history: List[float] = []

        for step in range(steps):
            t_rem = total_time_sec - (step * dt)
            state = AvellanedaStoikovState(
                mid_price=current_price,
                inventory=q,
                time_remaining_sec=t_rem,
                risk_aversion_gamma=gamma,
                volatility_sigma=sigma,
                arrival_intensity_A=A,
                price_sensitivity_k=k,
            )
            quote = self.compute_quote(state)
            quotes.append(quote)

            # Poisson arrival probabilities over interval dt
            # lambda(delta) = A * exp(-k * delta)
            lambda_bid = A * math.exp(-k * max(0.01, quote.bid_spread))
            lambda_ask = A * math.exp(-k * max(0.01, quote.ask_spread))

            prob_bid_fill = 1.0 - math.exp(-lambda_bid * dt)
            prob_ask_fill = 1.0 - math.exp(-lambda_ask * dt)

            # Check for fills
            if prng.random() < prob_bid_fill:
                # Buy fill: cash decreases by quote.optimal_bid, inventory increases
                cash -= quote.optimal_bid
                q += 1
                trades_executed += 1

            if prng.random() < prob_ask_fill:
                # Sell fill: cash increases by quote.optimal_ask, inventory decreases
                cash += quote.optimal_ask
                q -= 1
                trades_executed += 1

            # Arithmetic Brownian Motion mid-price update
            # dS = sigma * sqrt(dt) * Z
            z = prng.gauss(0.0, 1.0)
            current_price += sigma * math.sqrt(dt) * z

            # Total mark-to-market PnL = cash + inventory * current_price
            mtm_pnl = cash + (q * current_price)
            pnl_history.append(mtm_pnl)

        final_pnl = pnl_history[-1] if pnl_history else 0.0
        final_inv_val = q * current_price

        # Calculate Sharpe ratio and drawdown
        returns = []
        for i in range(1, len(pnl_history)):
            diff = pnl_history[i] - pnl_history[i - 1]
            returns.append(diff)

        mean_ret = sum(returns) / len(returns) if returns else 0.0
        var_ret = sum((r - mean_ret) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 1.0
        std_ret = math.sqrt(var_ret) if var_ret > 0 else 1.0
        annualized_sharpe = (mean_ret / std_ret) * math.sqrt(steps) if std_ret > 0 else 0.0

        # Maximum drawdown
        peak = -float("inf")
        max_dd = 0.0
        for pnl in pnl_history:
            if pnl > peak:
                peak = pnl
            dd = peak - pnl
            if dd > max_dd:
                max_dd = dd

        result = MarketMakingSimulationResult(
            total_quotes_generated=len(quotes),
            total_trades=trades_executed,
            final_inventory=q,
            inventory_pnl=final_inv_val,
            spread_pnl=cash,
            total_pnl=final_pnl,
            sharpe_ratio=annualized_sharpe,
            max_drawdown=max_dd,
        )
        return result, quotes
