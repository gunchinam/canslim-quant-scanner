"""Valuation Engine: 3-Stage DCF, Relative Valuation (PER/PBR/EV-EBITDA), Reverse DCF.

Supports:
- 3-Stage Discounted Cash Flow (DCF) with sensitivity range
- Relative valuation via PER, PBR, EV/EBITDA multiples
- Reverse DCF: binary search for implied growth rate at current price
- Composite fair value range and discount percentage
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ValuationResult:
    """Container for all valuation outputs.

    Attributes:
        dcf_value: Base DCF intrinsic value per share (WACC as discount rate).
        dcf_low: DCF value using WACC + 1% (conservative / lower bound).
        dcf_high: DCF value using WACC - 1% (optimistic / upper bound).
        per_fair: PER-based fair value (EPS * per_multiple).
        pbr_fair: PBR-based fair value (Book Value * pbr_multiple).
        ev_ebitda_fair: EV/EBITDA-based fair value (EBITDA * ev_ebitda_multiple).
        reverse_dcf_growth: Implied Stage-1 growth rate at current price.
        fair_value_range: (dcf_low, weighted_mid, dcf_high).
        discount_pct: Upside/downside from current price to weighted midpoint (%).
        method_scores: Raw valuation estimates keyed by method name.
    """

    dcf_value: float
    dcf_low: float
    dcf_high: float
    per_fair: float
    pbr_fair: float
    ev_ebitda_fair: float
    reverse_dcf_growth: float
    fair_value_range: tuple[float, float, float]
    discount_pct: float
    method_scores: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal DCF helper
# ---------------------------------------------------------------------------


def _dcf_value(
    fcf: float,
    wacc: float,
    growth_stage1: float,
    growth_stage2: float,
    terminal_growth: float,
) -> float:
    """Compute 3-Stage DCF intrinsic value.

    Stage 1: 5 years at ``growth_stage1``.
    Stage 2: 5 years at ``growth_stage2``.
    Terminal: Gordon-Growth perpetuity discounted back.

    Args:
        fcf: Free cash flow (base year).
        wacc: Weighted average cost of capital.
        growth_stage1: Annual growth rate for Stage 1.
        growth_stage2: Annual growth rate for Stage 2.
        terminal_growth: Perpetual terminal growth rate.

    Returns:
        Intrinsic value, or 0.0 on any arithmetic error.
    """
    try:
        if wacc <= terminal_growth:
            return 0.0

        pv: float = 0.0
        cf: float = fcf

        # Stage 1: years 1-5
        for t in range(1, 6):
            cf = cf * (1.0 + growth_stage1)
            pv += cf / math.pow(1.0 + wacc, t)

        # Stage 2: years 6-10
        for t in range(6, 11):
            cf = cf * (1.0 + growth_stage2)
            pv += cf / math.pow(1.0 + wacc, t)

        # Terminal value at end of year 10
        terminal_cf: float = cf * (1.0 + terminal_growth)
        terminal_value: float = terminal_cf / (wacc - terminal_growth)
        pv += terminal_value / math.pow(1.0 + wacc, 10)

        return pv
    except (ZeroDivisionError, ValueError, OverflowError):
        return 0.0


# ---------------------------------------------------------------------------
# Reverse DCF via binary search
# ---------------------------------------------------------------------------


def _reverse_dcf_growth(
    target_price: float,
    fcf: float,
    wacc: float,
    growth_stage2: float,
    terminal_growth: float,
    tolerance: float = 0.001,
    low: float = 0.0,
    high: float = 1.0,
    max_iter: int = 64,
) -> float:
    """Binary-search for the Stage-1 growth rate implied by ``target_price``.

    Args:
        target_price: Current market price to match.
        fcf: Base free cash flow.
        wacc: Discount rate.
        growth_stage2: Fixed Stage-2 growth rate used during search.
        terminal_growth: Fixed terminal growth rate.
        tolerance: Convergence threshold on the growth rate.
        low: Lower bound of search range.
        high: Upper bound of search range.
        max_iter: Maximum iterations before returning best estimate.

    Returns:
        Implied Stage-1 growth rate in [0, 1], or 0.0 on error.
    """
    try:
        if target_price <= 0.0 or fcf == 0.0:
            return 0.0

        for _ in range(max_iter):
            mid: float = (low + high) / 2.0
            estimated: float = _dcf_value(
                fcf, wacc, mid, growth_stage2, terminal_growth
            )
            if abs(high - low) < tolerance:
                return mid
            if estimated < target_price:
                low = mid
            else:
                high = mid

        return (low + high) / 2.0
    except (ZeroDivisionError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    ticker: str,
    current_price: float,
    financials: dict[str, Any],
    wacc: float = 0.10,
    growth_stage1: float = 0.15,
    growth_stage2: float = 0.08,
    terminal_growth: float = 0.03,
    per_multiple: float = 15.0,
    pbr_multiple: float = 1.5,
    ev_ebitda_multiple: float = 10.0,
) -> ValuationResult:
    """Run a composite valuation for ``ticker``.

    Args:
        ticker: Stock ticker symbol (informational; not used in math).
        current_price: Current market price per share.
        financials: Dict containing any of:
            - ``"fcf"``: Free cash flow (base year).
            - ``"eps"``: Earnings per share.
            - ``"book_value"``: Book value per share.
            - ``"ebitda"``: EBITDA (absolute, same units as price).
        wacc: Weighted average cost of capital (default 10%).
        growth_stage1: Stage-1 (years 1-5) annual growth rate (default 15%).
        growth_stage2: Stage-2 (years 6-10) annual growth rate (default 8%).
        terminal_growth: Terminal perpetual growth rate (default 3%).

    Returns:
        A :class:`ValuationResult` with all computed metrics.
    """
    fcf: float = float(financials.get("fcf", 0) or 0)
    eps: float = float(financials.get("eps", 0) or 0)
    book_value: float = float(financials.get("book_value", 0) or 0)
    ebitda: float = float(financials.get("ebitda", 0) or 0)
    shares: float = float(financials.get("shares_outstanding", financials.get("shares", 0)) or 0)

    # 총액 → 주당 정규화: shares가 있으면 무조건 per-share로 변환
    if shares > 0:
        if fcf != 0:
            fcf = fcf / shares
        if ebitda != 0:
            ebitda = ebitda / shares

    # --- 3-Stage DCF (base / low / high) ---
    dcf_base: float = _dcf_value(fcf, wacc, growth_stage1, growth_stage2, terminal_growth)
    dcf_low: float = _dcf_value(fcf, wacc + 0.01, growth_stage1, growth_stage2, terminal_growth)
    dcf_high: float = _dcf_value(fcf, wacc - 0.01, growth_stage1, growth_stage2, terminal_growth)

    # --- Relative valuation ---
    try:
        per_fair: float = eps * per_multiple
    except (ZeroDivisionError, ValueError):
        per_fair = 0.0

    try:
        pbr_fair: float = book_value * pbr_multiple
    except (ZeroDivisionError, ValueError):
        pbr_fair = 0.0

    try:
        ev_ebitda_fair: float = ebitda * ev_ebitda_multiple
    except (ZeroDivisionError, ValueError):
        ev_ebitda_fair = 0.0

    # --- Weighted midpoint ---
    try:
        weighted_mid: float = (
            dcf_base * 0.50
            + per_fair * 0.20
            + pbr_fair * 0.15
            + ev_ebitda_fair * 0.15
        )
    except (ZeroDivisionError, ValueError):
        weighted_mid = 0.0

    fair_value_range: tuple[float, float, float] = (dcf_low, weighted_mid, dcf_high)

    # --- Discount / premium to current price ---
    try:
        if current_price == 0.0:
            raise ZeroDivisionError
        discount_pct: float = (weighted_mid - current_price) / current_price * 100.0
    except (ZeroDivisionError, ValueError):
        discount_pct = 0.0

    # --- Reverse DCF ---
    reverse_growth: float = _reverse_dcf_growth(
        target_price=current_price,
        fcf=fcf,
        wacc=wacc,
        growth_stage2=growth_stage2,
        terminal_growth=terminal_growth,
    )

    # --- Method scores ---
    method_scores: dict[str, float] = {
        "DCF": dcf_base,
        "PER": per_fair,
        "PBR": pbr_fair,
        "EV_EBITDA": ev_ebitda_fair,
    }

    return ValuationResult(
        dcf_value=dcf_base,
        dcf_low=dcf_low,
        dcf_high=dcf_high,
        per_fair=per_fair,
        pbr_fair=pbr_fair,
        ev_ebitda_fair=ev_ebitda_fair,
        reverse_dcf_growth=reverse_growth,
        fair_value_range=fair_value_range,
        discount_pct=discount_pct,
        method_scores=method_scores,
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Samsung Electronics (005930.KS) — approximate FY2023 figures
    # Units: KRW per share / absolute KRW billions normalised to per-share basis
    # FCF proxy: operating CF - capex ≈ 4,500 KRW/share
    samsung_financials: dict[str, float] = {
        "fcf": 4_500,        # KRW per share
        "eps": 4_344,        # KRW per share (FY2023)
        "book_value": 52_000,  # KRW per share (approx)
        "ebitda": 8_200,     # KRW per share (approx)
    }

    current_price: float = 78_500  # KRW (approximate market price)

    result: ValuationResult = run(
        ticker="005930",
        current_price=current_price,
        financials=samsung_financials,
        wacc=0.10,
        growth_stage1=0.15,
        growth_stage2=0.08,
        terminal_growth=0.03,
    )

    print("=" * 60)
    print("  Samsung Electronics (005930) - Valuation Summary")
    print("=" * 60)
    print(f"  Current Price      : {current_price:>12,.0f} KRW")
    print()
    print(f"  DCF Value (base)   : {result.dcf_value:>12,.0f} KRW")
    print(f"  DCF Low  (WACC+1%) : {result.dcf_low:>12,.0f} KRW")
    print(f"  DCF High (WACC-1%) : {result.dcf_high:>12,.0f} KRW")
    print()
    print(f"  PER Fair Value     : {result.per_fair:>12,.0f} KRW")
    print(f"  PBR Fair Value     : {result.pbr_fair:>12,.0f} KRW")
    print(f"  EV/EBITDA Fair     : {result.ev_ebitda_fair:>12,.0f} KRW")
    print()
    lo, mid, hi = result.fair_value_range
    print(f"  Fair Value Range   : {lo:,.0f} ~ {mid:,.0f} ~ {hi:,.0f} KRW")
    print(f"  Discount / Premium : {result.discount_pct:>+.2f}%")
    print()
    print(f"  Implied Growth (Reverse DCF): {result.reverse_dcf_growth * 100:.2f}%")
    print()
    print("  Method Scores:")
    for method, score in result.method_scores.items():
        print(f"    {method:<12}: {score:>12,.0f} KRW")
    print("=" * 60)
