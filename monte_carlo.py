"""GBM 기반 Monte Carlo 시뮬레이션 엔진.

Geometric Brownian Motion(GBM)을 활용하여 주가 경로를 시뮬레이션하고
확률적 가격 밴드, 시나리오 분석, EV 가격을 산출합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PriceBand:
    """특정 미래 시점(days)의 시뮬레이션 가격 분포 백분위수.

    Attributes:
        days: 현재 시점으로부터의 거래일 수.
        p5: 5번째 백분위수 가격.
        p25: 25번째 백분위수 가격.
        p50: 50번째 백분위수 가격(중앙값).
        p75: 75번째 백분위수 가격.
        p95: 95번째 백분위수 가격.
    """

    days: int
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass
class Scenario:
    """단일 시나리오의 요약 정보.

    Attributes:
        name: 시나리오 이름 (예: "Bull", "Base", "Bear").
        prob: 발생 확률 (0~1 범위).
        target_price: 해당 시나리오의 목표 가격.
        key_driver: 가격 움직임의 핵심 동인 설명.
        return_pct: 현재 가격 대비 수익률(%).
    """

    name: str
    prob: float
    target_price: float
    key_driver: str
    return_pct: float


@dataclass
class MonteCarloResult:
    """Monte Carlo 시뮬레이션 전체 결과.

    Attributes:
        bands: 시점별 가격 분포 밴드 목록 (days=30, 90, 180).
        scenarios: Bull / Base / Bear 시나리오 목록.
        ev_price: 시나리오 확률 가중 기댓값 가격.
        ev_return_pct: ev_price 기준 기댓값 수익률(%).
        premortem_risks: 사전 실패 시나리오 리스크 항목 3개.
        signpost_kpis: 모니터링 기준 KPI 항목 5개.
    """

    bands: list[PriceBand]
    scenarios: list[Scenario]
    ev_price: float
    ev_return_pct: float
    premortem_risks: list[str] = field(default_factory=list)
    signpost_kpis: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PREMORTEM_RISKS: list[str] = [
    "거시경제 충격으로 인한 멀티플 급락",
    "실적 미스 연속으로 인한 신뢰 붕괴",
    "섹터 로테이션으로 인한 수급 이탈",
]

_SIGNPOST_KPIS: list[str] = [
    "RSI 30 하회 → 추가 하락 경계",
    "20MA 이탈 → 추세 전환 경계",
    "거래량 급증 동반 이탈 → 기관 매도 신호",
    "EPS 컨센서스 하향 조정",
    "외인 순매도 10일 연속",
]

_BAND_DAYS: list[int] = [30, 90, 180]
_TRADING_DAYS_PER_YEAR: float = 252.0

_SCENARIO_DEFINITIONS: list[tuple[str, float, str]] = [
    # (name, prob, key_driver)
    ("Bull", 0.25, "강한 실적 모멘텀과 섹터 선호도 상승으로 멀티플 확장"),
    ("Base", 0.50, "컨센서스 실적 달성 및 시장 평균 수준의 밸류에이션 유지"),
    ("Bear", 0.25, "매크로 역풍 및 실적 하향 조정으로 디레이팅 압력"),
]


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------


def _simulate_gbm(
    current_price: float,
    mu: float,
    sigma: float,
    n_days: int,
    n_simulations: int,
) -> np.ndarray:
    """GBM(기하 브라운 운동) 경로를 시뮬레이션합니다.

    dS = S * (mu * dt + sigma * sqrt(dt) * Z) 를 이산화하면:
        S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)

    exp()를 사용하므로 음수 가격은 원천적으로 발생하지 않습니다.

    Args:
        current_price: 현재(시뮬레이션 시작) 주가.
        mu: 연간 기대 수익률(드리프트).
        sigma: 연간 변동성.
        n_days: 시뮬레이션할 거래일 수.
        n_simulations: 생성할 경로 수.

    Returns:
        shape (n_simulations, n_days + 1) 배열.
        각 행이 하나의 가격 경로이며, 열 0은 current_price 입니다.
    """
    dt: float = 1.0 / _TRADING_DAYS_PER_YEAR

    # shape: (n_simulations, n_days)
    z: np.ndarray = np.random.standard_normal((n_simulations, n_days))

    # 로그 수익률 증분: (mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z
    log_returns: np.ndarray = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z

    # 누적 합 → exp()로 가격 경로 복원
    cum_log_returns: np.ndarray = np.cumsum(log_returns, axis=1)

    # shape: (n_simulations, n_days + 1)
    paths: np.ndarray = np.empty((n_simulations, n_days + 1), dtype=np.float64)
    paths[:, 0] = current_price
    paths[:, 1:] = current_price * np.exp(cum_log_returns)

    return paths


def _build_price_band(paths: np.ndarray, day: int) -> PriceBand:
    """특정 날짜의 가격 분포에서 PriceBand를 생성합니다.

    Args:
        paths: shape (n_simulations, n_days + 1) 경로 배열.
        day: 열 인덱스 (거래일 수).

    Returns:
        해당 날짜의 PriceBand 인스턴스.
    """
    prices_at_day: np.ndarray = paths[:, day]
    p5, p25, p50, p75, p95 = np.percentile(prices_at_day, [5, 25, 50, 75, 95])
    return PriceBand(
        days=day,
        p5=float(p5),
        p25=float(p25),
        p50=float(p50),
        p75=float(p75),
        p95=float(p95),
    )


def _build_scenarios(
    paths: np.ndarray,
    current_price: float,
    reference_day: int,
) -> list[Scenario]:
    """180일 시점 시뮬레이션 결과를 기반으로 Bull/Base/Bear 시나리오를 생성합니다.

    - Bull  : p95 시뮬레이션(상위 5%) 중앙값, prob=0.25
    - Base  : p50 시뮬레이션(전체) 중앙값, prob=0.50
    - Bear  : p5  시뮬레이션(하위 5%) 중앙값, prob=0.25

    Args:
        paths: shape (n_simulations, n_days + 1) 경로 배열.
        current_price: 현재 주가(수익률 계산 기준).
        reference_day: 시나리오 기준 날짜 열 인덱스 (보통 180).

    Returns:
        Scenario 인스턴스 3개 목록 [Bull, Base, Bear].
    """
    prices_at_ref: np.ndarray = paths[:, reference_day]

    # 백분위수 임계값
    p5_threshold: float = float(np.percentile(prices_at_ref, 5))
    p95_threshold: float = float(np.percentile(prices_at_ref, 95))

    # 각 집단 추출
    bull_prices: np.ndarray = prices_at_ref[prices_at_ref >= p95_threshold]
    base_prices: np.ndarray = prices_at_ref
    bear_prices: np.ndarray = prices_at_ref[prices_at_ref <= p5_threshold]

    target_prices: list[float] = [
        float(np.median(bull_prices)),
        float(np.median(base_prices)),
        float(np.median(bear_prices)),
    ]

    scenarios: list[Scenario] = []
    for (name, prob, key_driver), target_price in zip(
        _SCENARIO_DEFINITIONS, target_prices
    ):
        return_pct: float = (target_price / current_price - 1) * 100
        scenarios.append(
            Scenario(
                name=name,
                prob=prob,
                target_price=target_price,
                key_driver=key_driver,
                return_pct=return_pct,
            )
        )

    return scenarios


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    ticker: str,
    current_price: float,
    hist_returns: np.ndarray,
    mu: float,
    sigma: float,
    n_simulations: int = 10000,
) -> MonteCarloResult:
    """GBM Monte Carlo 시뮬레이션을 실행하여 MonteCarloResult를 반환합니다.

    Args:
        ticker: 종목 코드 또는 이름 (현재는 로깅/식별 용도).
        current_price: 현재 주가 (양수여야 합니다).
        hist_returns: 과거 일별 수익률 배열 (참고용, 직접 사용 안 함).
        mu: 연간 기대 수익률(드리프트). 예: 0.10 → 연 10%.
        sigma: 연간 변동성. 예: 0.25 → 연 25%.
        n_simulations: 시뮬레이션 경로 수. 기본값 10,000.

    Returns:
        MonteCarloResult 인스턴스.

    Raises:
        ValueError: current_price 가 0 이하이거나 sigma 가 0 이하인 경우.
    """
    if current_price <= 0:
        raise ValueError(f"current_price는 양수여야 합니다. 입력값: {current_price}")
    if sigma <= 0:
        raise ValueError(f"sigma는 양수여야 합니다. 입력값: {sigma}")

    # 재현성 보장
    np.random.seed(42)

    # 최대 시뮬레이션 기간 = 가장 긴 밴드 days
    max_days: int = max(_BAND_DAYS)

    # GBM 경로 생성 — exp() 사용으로 음수 가격 원천 차단
    paths: np.ndarray = _simulate_gbm(
        current_price=current_price,
        mu=mu,
        sigma=sigma,
        n_days=max_days,
        n_simulations=n_simulations,
    )

    # 가격 밴드 구성
    bands: list[PriceBand] = [_build_price_band(paths, day) for day in _BAND_DAYS]

    # 시나리오 구성 (180일 기준)
    reference_day: int = max_days
    scenarios: list[Scenario] = _build_scenarios(paths, current_price, reference_day)

    # 기댓값(EV) 계산
    ev_price: float = sum(s.prob * s.target_price for s in scenarios)
    ev_return_pct: float = (ev_price / current_price - 1) * 100

    return MonteCarloResult(
        bands=bands,
        scenarios=scenarios,
        ev_price=ev_price,
        ev_return_pct=ev_return_pct,
        premortem_risks=list(_PREMORTEM_RISKS),
        signpost_kpis=list(_SIGNPOST_KPIS),
    )
