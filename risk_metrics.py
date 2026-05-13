"""Risk metrics engine for stock scanner.

Provides VaR (Historical Simulation), Piotroski F-Score, Altman Z-Score,
stress testing, and portfolio weight recommendations.

Python 3.13+, numpy only (no scipy).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

import numpy as np


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VaRResult:
    """Value-at-Risk and related risk metrics.

    All var/cvar values are expressed as negative percentages (e.g. -2.3).
    Volatility values are expressed as positive percentages.
    """

    var_95_1d: float
    var_99_1d: float
    var_95_1w: float
    var_99_1w: float
    var_95_1m: float
    var_99_1m: float
    cvar_95: float
    annual_vol: float
    max_dd: float
    sharpe: float
    sortino: float


@dataclass
class StressResult:
    """Result of a single stress-test scenario."""

    scenario: str
    price_impact_pct: float
    description: str


@dataclass
class RiskReport:
    """Consolidated risk report for a single ticker."""

    var: VaRResult
    stress_tests: List[StressResult]
    piotroski_score: int
    altman_z: float
    recommended_weight_pct: float


# ---------------------------------------------------------------------------
# Fixed stress-test scenarios
# ---------------------------------------------------------------------------

_STRESS_SCENARIOS: list[tuple[str, float, str]] = [
    ("금리+100bp",    -5.0,  "기준금리 100bp 인상"),
    ("환율+10%",      -3.0,  "원달러 +10% 약세"),
    ("글로벌CAPEX감축", -8.0, "글로벌 설비투자 급감"),
    ("정책쇼크",     -12.0,  "정부 규제/세제 급변"),
    ("공급망차질",    -6.0,  "주요 원자재 공급 중단"),
]


# ---------------------------------------------------------------------------
# VaR helpers
# ---------------------------------------------------------------------------


def _compute_var(hist_returns: np.ndarray) -> VaRResult:
    """Compute historical-simulation VaR and complementary metrics.

    Args:
        hist_returns: 1-D array of daily log or simple returns (e.g. 0.01 = +1%).

    Returns:
        Populated VaRResult instance.
    """
    returns = np.asarray(hist_returns, dtype=float)

    # --- 1-day VaR (negative %) ---
    var_95_1d_frac = float(np.percentile(returns, 5))
    var_99_1d_frac = float(np.percentile(returns, 1))

    # --- Scale to weekly / monthly ---
    sqrt5  = math.sqrt(5)
    sqrt21 = math.sqrt(21)

    var_95_1w = var_95_1d_frac * sqrt5  * 100
    var_99_1w = var_99_1d_frac * sqrt5  * 100
    var_95_1m = var_95_1d_frac * sqrt21 * 100
    var_99_1m = var_99_1d_frac * sqrt21 * 100

    var_95_1d_pct = var_95_1d_frac * 100
    var_99_1d_pct = var_99_1d_frac * 100

    # --- CVaR (Expected Shortfall) at 95% ---
    tail = returns[returns <= var_95_1d_frac]
    cvar_95 = float(tail.mean()) * 100 if len(tail) > 0 else var_95_1d_pct

    # --- Annual volatility ---
    annual_vol = float(returns.std()) * math.sqrt(252) * 100

    # --- Maximum drawdown via cumulative product ---
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    drawdown = (cum - peak) / peak  # <= 0
    max_dd = float(drawdown.min()) * 100  # negative %

    # --- Annual return ---
    annual_return = ((1.0 + float(returns.mean())) ** 252 - 1.0) * 100

    # --- Sharpe (risk-free = 3%) ---
    sharpe = (annual_return - 3.0) / annual_vol if annual_vol != 0.0 else 0.0

    # --- Sortino ---
    neg = returns[returns < 0]
    if len(neg) > 0 and neg.std() != 0.0:
        downside_vol = float(neg.std()) * math.sqrt(252) * 100
        sortino = (annual_return - 3.0) / downside_vol
    else:
        sortino = 0.0

    return VaRResult(
        var_95_1d=var_95_1d_pct,
        var_99_1d=var_99_1d_pct,
        var_95_1w=var_95_1w,
        var_99_1w=var_99_1w,
        var_95_1m=var_95_1m,
        var_99_1m=var_99_1m,
        cvar_95=cvar_95,
        annual_vol=annual_vol,
        max_dd=max_dd,
        sharpe=sharpe,
        sortino=sortino,
    )


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------


def _run_stress_tests() -> List[StressResult]:
    """Return fixed stress-test results.

    Returns:
        List of StressResult for each predefined scenario.
    """
    return [
        StressResult(scenario=name, price_impact_pct=impact, description=desc)
        for name, impact, desc in _STRESS_SCENARIOS
    ]


# ---------------------------------------------------------------------------
# Piotroski F-Score
# ---------------------------------------------------------------------------


def piotroski_f_score(financials: dict) -> int:
    """Compute the Piotroski F-Score (0 – 9).

    Each of the 9 criteria awards 1 point. Missing keys default to 0 (criterion
    fails silently rather than raising an exception).

    Expected keys in *financials*:
        roa (float): Return on assets, current period.
        roa_prev (float): Return on assets, prior period.
        cfo (float): Cash flow from operations.
        total_assets (float): Total assets (current period).
        accrual_roa (float): Optional override; if absent derived from cfo/assets.
        leverage (float): Long-term debt / total assets, current.
        leverage_prev (float): Long-term debt / total assets, prior.
        current_ratio (float): Current ratio, current period.
        current_ratio_prev (float): Current ratio, prior period.
        shares_outstanding (float): Shares outstanding, current period.
        shares_outstanding_prev (float): Shares outstanding, prior period.
        gross_margin (float): Gross margin (%), current period.
        gross_margin_prev (float): Gross margin (%), prior period.
        asset_turnover (float): Revenue / assets, current period.
        asset_turnover_prev (float): Revenue / assets, prior period.

    Args:
        financials: Dictionary of financial metrics.

    Returns:
        Integer score in range [0, 9].
    """
    score = 0
    g = financials.get  # shorthand

    # --- Profitability (4 points) ---

    # F1: ROA > 0
    roa = g("roa", None)
    if roa is not None and roa > 0:
        score += 1

    # F2: CFO > 0
    cfo = g("cfo", None)
    if cfo is not None and cfo > 0:
        score += 1

    # F3: Delta ROA > 0
    roa_prev = g("roa_prev", None)
    if roa is not None and roa_prev is not None and (roa - roa_prev) > 0:
        score += 1

    # F4: Accrual — CFO/assets > ROA (quality of earnings)
    total_assets = g("total_assets", None)
    if cfo is not None and total_assets and total_assets != 0 and roa is not None:
        accrual = cfo / total_assets
        if accrual > roa:
            score += 1

    # --- Leverage / Liquidity / Source of Funds (3 points) ---

    # F5: Delta leverage < 0 (decreasing debt ratio is good)
    leverage      = g("leverage", None)
    leverage_prev = g("leverage_prev", None)
    if leverage is not None and leverage_prev is not None:
        if (leverage - leverage_prev) < 0:
            score += 1

    # F6: Delta current ratio > 0
    cr      = g("current_ratio", None)
    cr_prev = g("current_ratio_prev", None)
    if cr is not None and cr_prev is not None and (cr - cr_prev) > 0:
        score += 1

    # F7: No dilution — shares outstanding did not increase
    shares      = g("shares_outstanding", None)
    shares_prev = g("shares_outstanding_prev", None)
    if shares is not None and shares_prev is not None and shares <= shares_prev:
        score += 1

    # --- Operating Efficiency (2 points) ---

    # F8: Delta gross margin > 0
    gm      = g("gross_margin", None)
    gm_prev = g("gross_margin_prev", None)
    if gm is not None and gm_prev is not None and (gm - gm_prev) > 0:
        score += 1

    # F9: Delta asset turnover > 0
    at_      = g("asset_turnover", None)
    at_prev  = g("asset_turnover_prev", None)
    if at_ is not None and at_prev is not None and (at_ - at_prev) > 0:
        score += 1

    return score


# ---------------------------------------------------------------------------
# Altman Z-Score
# ---------------------------------------------------------------------------


def altman_z_score(financials: dict) -> float:
    """Compute the Altman Z-Score for public manufacturing firms.

    Formula:
        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

    where:
        X1 = working_capital / total_assets
        X2 = retained_earnings / total_assets
        X3 = ebit / total_assets
        X4 = equity_mv / (total_liabilities + 1)   (+1 avoids division by zero
        X5 = revenue / total_assets

    Interpretation:
        Z > 2.99  -> Safe zone
        1.81 < Z <= 2.99 -> Grey zone
        Z <= 1.81 -> Distress zone

    Missing keys default to 0 (ratio treated as 0).

    Args:
        financials: Dictionary of financial metrics.

    Returns:
        Altman Z-Score as a float.
    """
    g = financials.get

    total_assets    = g("total_assets", 0) or 0
    total_liab      = g("total_liabilities", 0) or 0
    working_capital = g("working_capital", 0) or 0
    retained_earn   = g("retained_earnings", 0) or 0
    ebit            = g("ebit", 0) or 0
    equity_mv       = g("equity_mv", 0) or 0
    revenue         = g("revenue", 0) or 0

    if total_assets == 0:
        # Cannot compute meaningful ratios; return neutral score
        return 0.0

    x1 = working_capital / total_assets
    x2 = retained_earn   / total_assets
    x3 = ebit            / total_assets
    x4 = equity_mv       / (total_liab + 1)
    x5 = revenue         / total_assets

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    return float(z)


# ---------------------------------------------------------------------------
# Recommended weight
# ---------------------------------------------------------------------------


def _recommended_weight(sharpe: float) -> float:
    """Compute recommended portfolio weight clamped to [0, 20]%.

    Args:
        sharpe: Sharpe ratio.

    Returns:
        Weight in percent.
    """
    return max(0.0, min(20.0, sharpe * 5.0))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    ticker: str,
    hist_returns: np.ndarray,
    current_price: float,
    financials: dict,
    total_portfolio_value: float = 100_000_000,
) -> RiskReport:
    """Generate a complete risk report for a ticker.

    Args:
        ticker: Stock ticker symbol (informational; not used in calculations).
        hist_returns: 1-D numpy array of daily returns (decimal, e.g. 0.01 = +1%).
        current_price: Most recent closing price (informational).
        financials: Dictionary of financial statement data. See
            :func:`piotroski_f_score` and :func:`altman_z_score` for expected keys.
        total_portfolio_value: Total portfolio value in KRW (default 100,000,000).
            Currently informational; used to contextualise position sizing.

    Returns:
        RiskReport containing VaR metrics, stress tests, Piotroski F-Score,
        Altman Z-Score, and recommended portfolio weight.
    """
    returns_arr = np.asarray(hist_returns, dtype=float)

    var_result    = _compute_var(returns_arr)
    stress_tests  = _run_stress_tests()
    f_score       = piotroski_f_score(financials)
    z_score       = altman_z_score(financials)
    weight        = _recommended_weight(var_result.sharpe)

    return RiskReport(
        var=var_result,
        stress_tests=stress_tests,
        piotroski_score=f_score,
        altman_z=z_score,
        recommended_weight_pct=weight,
    )
