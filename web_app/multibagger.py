"""멀티배거 파인더 — 순수 평가/점수 함수."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# F1~F8 디폴트 임계
DEFAULTS = {
    "F1_MCAP_MIN": 200_000_000,
    "F1_MCAP_MAX": 2_000_000_000,
    "F3_ROIC_MIN": 0.10,
    "F4_FCF_YIELD_MIN": 0.05,
    "F4_PB_MAX": 3.0,
    "F5_REVENUE_YOY_MIN": 0.05,
    "F7_ICR_MIN": 3.0,
    "F7_DEBT_EBITDA_MAX": 3.0,
    "F7_ICR_MIN_HIRATE": 4.0,
    "F7_DEBT_EBITDA_MAX_HIRATE": 2.5,
    "F7_HIRATE_DGS10_PCT": 4.0,
    "F8_FROM_52W_HIGH_MIN": -0.50,
    "F8_FROM_52W_HIGH_MAX": -0.10,
    "F8_1M_RETURN_MAX": 0.30,
}

CORE_GATES_REQUIRED = ("F1", "F2", "F8")  # WATCH도 필수 통과
CORE_GATES_OPTIONAL = ("F3", "F4", "F5", "F6", "F7")  # WATCH는 1~2개 부족 허용
ALL_GATES = CORE_GATES_REQUIRED + CORE_GATES_OPTIONAL


@dataclass
class Fundamentals:
    """게이트 평가에 필요한 모든 입력. 결측은 None."""
    market_cap: Optional[float] = None
    ebitda: Optional[float] = None
    fcf: Optional[float] = None
    roic: Optional[float] = None
    roic_prev: Optional[float] = None
    fcf_yield: Optional[float] = None
    pb: Optional[float] = None
    revenue_yoy: Optional[float] = None
    revenue_yoy_prev: Optional[float] = None  # B4용 (1년 전 YoY)
    ebitda_yoy: Optional[float] = None
    fcf_yoy: Optional[float] = None
    assets_yoy: Optional[float] = None
    icr: Optional[float] = None
    debt_ebitda: Optional[float] = None
    from_52w_high: Optional[float] = None  # 음수 (예: -0.20 = 20% 빠짐)
    return_1m: Optional[float] = None
    sector: Optional[str] = None
    insider_net_buy_3m: Optional[float] = None
    buyback_yield_ttm: Optional[float] = None
    capex_yoy: Optional[float] = None  # F6 N/A 판정용
    dgs10_pct: Optional[float] = None
