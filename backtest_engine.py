"""
backtest_engine.py
------------------
5년 룰베이스 백테스트 엔진.

Dependencies: Python 3.13, numpy, pandas
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """백테스트 결과 컨테이너."""

    win_rate: float          # 승률 (%)
    payoff_ratio: float      # 손익비
    sharpe: float            # 샤프 지수 (rf=0, 연환산)
    max_drawdown: float      # 최대 낙폭 (%, 음수)
    total_return: float      # 총 수익률 (%)
    n_trades: int            # 총 거래 수
    avg_holding_days: float  # 평균 보유일
    annual_return: float     # 단순 연환산 수익률 (%)
    summary: str             # 요약 문자열


# ---------------------------------------------------------------------------
# Internal trade record
# ---------------------------------------------------------------------------


class _Trade(NamedTuple):
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    return_pct: float        # 수수료 반영 후 수익률 (%)


# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------


def _sma(series: pd.Series, window: int) -> pd.Series:
    """단순 이동평균 (look-ahead bias 없음)."""
    return series.rolling(window).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """EWM 방식 RSI.

    look-ahead bias 방지: 각 시점에서 과거 데이터만 사용.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder smoothing = EWM with alpha = 1/period
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run(
    df: pd.DataFrame,
    initial_capital: float = 10_000_000,
) -> BacktestResult:
    """룰베이스 백테스트를 실행하고 결과를 반환한다.

    Args:
        df: OHLCV 데이터프레임.
            index=DatetimeIndex, columns=[Open, High, Low, Close, Volume].
        initial_capital: 초기 자본금 (원). 기본값 10,000,000.

    Returns:
        BacktestResult 인스턴스.

    Raises:
        ValueError: 필수 컬럼이 없거나 데이터가 부족할 때.
    """
    required_columns = {"Open", "High", "Low", "Close", "Volume"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"df에 필수 컬럼이 없습니다: {missing}")

    if len(df) < 30:
        raise ValueError("백테스트에 최소 30행 이상의 데이터가 필요합니다.")

    # 방어적 복사 및 정렬
    df = df.copy().sort_index()

    close: pd.Series = df["Close"].astype(float)
    volume: pd.Series = df["Volume"].astype(float)

    # ------------------------------------------------------------------
    # 지표 계산 (look-ahead bias 절대 금지 — shift()로 신호 생성 시점 분리)
    # ------------------------------------------------------------------
    sma20: pd.Series = _sma(close, 20)
    rsi14: pd.Series = _rsi(close, 14)
    vol_avg30: pd.Series = volume.rolling(30).mean()

    # 전일 RSI (신호 판단에 사용 — 당일 종가로 계산된 지표를 당일 매매에 쓰지 않음)
    # 매수 신호는 당일 종가 확정 후 다음 날 시가에 체결한다고 가정하지 않고,
    # 종가 기준 당일 신호로 처리하되 RSI 조건의 "이전값 < 45 AND 현재값 >= 45"는
    # shift(1)로 이전 봉 값을 참조한다.
    rsi14_prev: pd.Series = rsi14.shift(1)

    # ------------------------------------------------------------------
    # 신호 벡터 생성
    # ------------------------------------------------------------------
    buy_signal: pd.Series = (
        (close > sma20)
        & (volume > vol_avg30 * 1.3)
        & (rsi14_prev < 45)
        & (rsi14 >= 45)
    )

    sell_signal: pd.Series = (close < sma20 * 0.97) | (rsi14 > 75)

    # ------------------------------------------------------------------
    # 거래 시뮬레이션
    # ------------------------------------------------------------------
    SLIPPAGE_BUY = 1.0 - 0.001   # 매수 시 0.1% 비용
    SLIPPAGE_SELL = 1.0 - 0.001  # 매도 시 0.1% 비용

    capital: float = initial_capital
    in_position: bool = False
    entry_price: float = 0.0
    entry_date: pd.Timestamp | None = None

    trades: list[_Trade] = []

    # 포트폴리오 가치 시계열 (매일 기록)
    portfolio_values: list[float] = []
    dates: list[pd.Timestamp] = []

    for date, row in df.iterrows():
        date = pd.Timestamp(date)
        price = float(row["Close"])

        # 포지션 중 현재 가치 평가
        if in_position:
            current_value = capital / entry_price * price * SLIPPAGE_SELL
        else:
            current_value = capital

        portfolio_values.append(current_value)
        dates.append(date)

        # 매도 신호 처리 (포지션 있을 때)
        if in_position and sell_signal.loc[date]:
            # 매도 체결가 = 당일 종가 * 슬리피지
            exit_price_effective = price * SLIPPAGE_SELL
            shares = capital / (entry_price * SLIPPAGE_BUY)
            exit_capital = shares * exit_price_effective

            ret_pct = (exit_capital / capital - 1.0) * 100.0

            trades.append(
                _Trade(
                    entry_date=entry_date,
                    exit_date=date,
                    entry_price=entry_price,
                    exit_price=price,
                    return_pct=ret_pct,
                )
            )

            capital = exit_capital
            in_position = False
            entry_price = 0.0
            entry_date = None

            # 포트폴리오 가치 갱신 (매도 후)
            portfolio_values[-1] = capital

        # 매수 신호 처리 (포지션 없을 때)
        elif not in_position and buy_signal.loc[date]:
            # 매수 체결: 전액 투입, 수수료 0.1%
            entry_price = price  # 실제 진입가 (수수료는 capital 계산에 반영)
            entry_date = date
            in_position = True
            # capital 자체는 변하지 않고, 보유 수량 = capital / (price * SLIPPAGE_BUY)
            # 단, 간략화를 위해 capital을 수수료만큼 즉시 차감
            capital = capital * SLIPPAGE_BUY
            portfolio_values[-1] = capital  # 매수 후 즉시 평가

    # 잔존 포지션 처리 (마지막 날 종가로 강제 청산)
    if in_position:
        last_date = dates[-1]
        last_price = float(df["Close"].iloc[-1])
        exit_price_effective = last_price * SLIPPAGE_SELL
        shares = capital / (entry_price * SLIPPAGE_BUY) if entry_price != 0 else 0.0
        # 이미 위에서 capital에 SLIPPAGE_BUY를 반영했으므로
        # shares = capital / entry_price (SLIPPAGE_BUY는 capital에 녹아 있음)
        shares = capital / entry_price
        exit_capital = shares * exit_price_effective

        ret_pct = (exit_capital / capital - 1.0) * 100.0

        trades.append(
            _Trade(
                entry_date=entry_date,
                exit_date=last_date,
                entry_price=entry_price,
                exit_price=last_price,
                return_pct=ret_pct,
            )
        )
        capital = exit_capital
        portfolio_values[-1] = capital

    # ------------------------------------------------------------------
    # 지표 계산
    # ------------------------------------------------------------------
    n_trades: int = len(trades)
    total_days: int = len(df)

    # 총 수익률
    total_return: float = (capital / initial_capital - 1.0) * 100.0

    # 단순 연환산 수익률
    annual_return: float = total_return / total_days * 252 if total_days > 0 else 0.0

    # 승률 / 손익비
    if n_trades >= 2:
        wins = [t.return_pct for t in trades if t.return_pct > 0.0]
        losses = [t.return_pct for t in trades if t.return_pct <= 0.0]

        win_rate: float = len(wins) / n_trades * 100.0

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0

        if avg_loss != 0.0:
            payoff_ratio: float = avg_win / abs(avg_loss)
        else:
            payoff_ratio = float("inf") if avg_win > 0 else 0.0
    else:
        win_rate = 0.0
        payoff_ratio = 0.0

    # 평균 보유일
    if n_trades > 0:
        holding_days = [
            (t.exit_date - t.entry_date).days for t in trades
        ]
        avg_holding_days: float = float(np.mean(holding_days))
    else:
        avg_holding_days = 0.0

    # 최대 낙폭 (MDD)
    pv_array = np.array(portfolio_values, dtype=float)
    running_max = np.maximum.accumulate(pv_array)
    drawdowns = (pv_array - running_max) / running_max * 100.0
    max_drawdown: float = float(np.min(drawdowns))

    # 샤프 지수
    pv_series = pd.Series(portfolio_values, index=dates)
    daily_returns = pv_series.pct_change().dropna()

    if len(daily_returns) > 1 and daily_returns.std() != 0.0:
        sharpe: float = float(
            daily_returns.mean() / daily_returns.std() * math.sqrt(252)
        )
    else:
        sharpe = 0.0

    # 요약 문자열
    summary: str = (
        f"5Y 백테스트: 승률{win_rate:.0f}% "
        f"손익비{payoff_ratio:.1f} "
        f"MDD{max_drawdown:.0f}% "
        f"연수익률{annual_return:+.0f}%"
    )

    return BacktestResult(
        win_rate=win_rate,
        payoff_ratio=payoff_ratio,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        total_return=total_return,
        n_trades=n_trades,
        avg_holding_days=avg_holding_days,
        annual_return=annual_return,
        summary=summary,
    )
