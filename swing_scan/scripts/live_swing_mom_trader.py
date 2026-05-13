"""scripts/live_swing_mom_trader.py
SWING-MOM 실시간 자동매매 (스윙 모드)

흐름 (시각은 모두 LIVE_PARAMS 참조 — 하드코드 금지):
  1. 장 시작 전: 유동성 점수, 유니버스 준비
  2. LIVE_PARAMS["entry_start"]~["entry_end"]: 5분봉 완성 직후 SWING-MOM 신호 감지 → KIS 시장가 매수
     (현 기본값: 09:30~14:30. 첫 5분봉 완성 시점이 09:30 이라 09:05 로 내려도 실효 없음)
  3. Multi-TP 포지션 관리 (RR=1.5 검증 완료):
     - tp1(1.5%) 도달 시 50% 청산, SL → breakeven
     - tp2(4.5%) 도달 시 잔여 청산
     - SL(-1.0%) 도달 시 전량 청산
  4. LIVE_PARAMS["entry_end"] 이후 신규 진입 금지, 기존 포지션만 관리
  5. EOD 강제 청산 비활성(기본) — EOD_FORCE_TIME = None.
     당일 청산 원할 때만 "HH:MM" 로 설정.
  6. time_stop_bars = 120 (SWING_MOM_DW_CONFIG 기준 ≈ 1.5거래일) 도달 시 time_stop 청산.
  7. 15:45 프로세스 종료 시 잔존 포지션은 오버나잇 보유 (재시작 전 잔고 reconcile 필요).

MR4와 동시 운영 가능 — 별도 프로세스, 별도 로그 파일.

실행:
  py -3 scripts/live_swing_mom_trader.py
  py -3 scripts/live_swing_mom_trader.py --risk_pct 0.01 --max_positions 6
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

import polars as pl

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # swing_scan/
sys.path.insert(0, _ROOT)

if getattr(sys.stdout, "buffer", None) is not None:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=True,
    )
if getattr(sys.stderr, "buffer", None) is not None:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=True,
    )

import requests
from execution.kis_client import get_client, IS_MOCK, BASE_URL
from utils.telegram_notifier import get_notifier
from utils.report_scheduler import ReportScheduler
from journal.trading_journal import TradingJournal
from journal.trade_event import TradeEvent
from engine.context_state import build_context_states
from strategies.intraday_swing_mom import (
    SWING_MOM_DW_CONFIG,
    _generate_signals_for_ticker,
    _calc_vwap_intraday,
    inspect_signal_bar_swing_mom,
    _ts_str,
    validate_tp_config,
)
from utils.liquidity_universe import (
    build_liquidity_universe,
    classify_price_floor,
    filter_price_floor_frames,
)

Path(os.path.join(_ROOT, "logs")).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(_ROOT, "logs", f"live_swing_mom_{date.today().isoformat()}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

# ── 슬리피지 추정 (체결 현실화) ────────────────────────────────────────────
# SL 시장가 체결 시 실제 fill은 저가보다 불리함 (bid 기준)
SLIPPAGE_RATE: float = 0.001

# ── 파라미터 ──────────────────────────────────────────────────────────────────
# SSOT = strategies/intraday_swing_mom.py::SWING_MOM_DW_CONFIG.
# 2026-04-16: TP/SL 스윕 → TP1=3.0% SL=fix_1.0% 2-tier TP+trailing 전환
#   OOS (2025~2026): PF=3.67, Sharpe=6.56, MDD=4.6%, R/R=2.25, WR=47.7%
#   IS  (2021~2024): PF=1.58, Sharpe=2.39, MDD=8.35%, Return=123% (R/R FAIL)
# 파라미터 변경은 DW_CONFIG에서만. 여기에 같은 키를 다시 적으면 SSOT 위반.
LIVE_PARAMS = {
    **SWING_MOM_DW_CONFIG,
    # Live 실동작 기준 override: 첫 5분봉 완성 시점이 09:30 이라 DW_CONFIG 의 09:05 는
    # 라이브에서 실효가 없다. 하드코드 대기 가드(기존 "09:28") 대신 이 값을 SSOT 로 삼아
    # 모든 시간 로직(대기 가드·로그)이 config 참조로 통일됨.
    "entry_start": "09:30",
    "default_equity": 10_000_000,  # 계좌가치 조회 실패 시 fallback (live 전용 키)
    # 2026-04-27 live override: 당일 재진입 차단 — 백테스트 locked=False 이지만
    # 실전에서 001290 3회 재진입(-4.97% 슬리피지) 사례 재발 방지.
    "prevent_same_day_reentry": True,
    # 2026-04-27 live override: 잔고 518만원 기준 6포지션은 자금 초과.
    # 포지션당 투입 ~260만원 × 3 = 780만원 (현실적 상한).
    "max_positions": 3,
    # 2026-04-27 백테스트 검증 완료: LIVE+unconditional IS R/R=2.061, OOS CAGR=129%
    # add_on_buy=True 복원 (unconditional, prevent_same_day_reentry=True 유지)
    "add_on_buy": True,
    # 2026-04-27 live override: 5분봉 SL은 캔들 종가 기반이라 시장가 체결 시
    # 실손이 sl_pct 초과. 오늘 실측 초과분 평균 ~0.22% → 0.0025 로 상향.
    "sl_slippage_pct": 0.0025,
    # 2026-04-27 live override: 백테스트 UNIVERSE_TOP_N=20 와 유니버스 크기 정렬.
    # 기본값 30은 Top-21~30 종목을 추가로 노출해 백테스트 비교 노이즈를 유발.
    "universe_n": 20,
}

def _compute_risk_levels(entry_price: float, params: dict) -> tuple[float, float, float]:
    # 0(또는 음수) 진입가는 SL/TP 를 모두 0 으로 만들어 다음 봉에 즉시 SL 발동(추정 -100% 손실)을
    # 야기한다. 호출부에서 새 포지션 생성을 차단해야 하므로 명시적으로 fail-fast.
    if entry_price is None or entry_price <= 0:
        raise ValueError(f"entry_price={entry_price} invalid — 새 포지션 생성을 중단하세요")
    sl_price = entry_price * (1 - params["sl_pct"])
    tp1_pct = params.get("tp1_pct")
    tp2_pct = params.get("tp2_pct")
    tp_pct = params.get("tp_pct", 0.12)

    if tp1_pct is not None:
        tp1_price = entry_price * (1 + tp1_pct)
        tp2_price = entry_price * (1 + tp2_pct) if tp2_pct else tp1_price
    else:
        tp1_price = entry_price * (1 + tp_pct)
        tp2_price = tp1_price

    return sl_price, tp1_price, tp2_price


# B2 fix: 매도 재시도 (engine/swing_mom_runner.py:982-997 패턴 준수)
#   - 최대 max_attempts 회 재시도, 실패 간격 retry_delay 초
#   - 모든 시도 실패 시 success=False 로 마지막 result 반환 (호출부가 상태 유지 결정)
#   - API 예외도 재시도 대상 (timeout/network flaps 자주 발생)
def _sell_market_with_retry(
    kis_client,
    ticker: str,
    qty: int,
    *,
    max_attempts: int = 3,
    retry_delay: float = 1.0,
    context: str = "",
):
    # 재시도 불필요한 오류 패턴 (이미 주문 접수됨을 의미)
    _NO_RETRY_MSGS = ("주문 가능한 수량", "수량을 초과", "보유수량 초과")

    last_result = {"success": False, "msg": "no attempts"}
    for attempt in range(1, max_attempts + 1):
        try:
            result = kis_client.sell_market(ticker, qty)
            if result and result.get("success"):
                if attempt > 1:
                    logger.info(
                        "  [sell재시도 성공] %s%s qty=%d attempt=%d",
                        ticker, f" ({context})" if context else "", qty, attempt,
                    )
                return result
            last_result = result or last_result
            msg = (result or {}).get("msg", "")
            msg_stripped = msg.strip()
            logger.warning(
                "  [sell재시도] %s%s 시도%d 실패: %s",
                ticker, f" ({context})" if context else "", attempt, msg,
            )
            # 이미 주문이 접수된 상태 → 재시도해도 같은 오류 → 즉시 중단
            if any(pat in msg_stripped for pat in _NO_RETRY_MSGS):
                logger.warning(
                    "  [sell중단] %s 수량초과 오류 — 기접수 주문 대기 중. 재시도 생략.",
                    ticker,
                )
                last_result["pending_order"] = True
                break
        except Exception as _sell_e:
            last_result = {"success": False, "msg": f"exception: {_sell_e}"}
            logger.warning(
                "  [sell재시도] %s%s 시도%d 예외: %s",
                ticker, f" ({context})" if context else "", attempt, _sell_e,
            )
        if attempt < max_attempts:
            time.sleep(retry_delay)
    logger.error(
        "  [sell최종실패] %s%s qty=%d max_attempts=%d msg=%s",
        ticker, f" ({context})" if context else "", qty, max_attempts,
        last_result.get("msg", ""),
    )
    return last_result


DATA_DIR  = os.path.join(_ROOT, "data", "minute")
DAILY_DIR = os.path.join(_ROOT, "data", "daily")
HISTORY_DAYS = 15   # context 빌드용 과거 데이터 로드 일수
# 스윙 모드: None = 당일 강제 청산 비활성화. 당일 청산 원할 때만 "HH:MM" 설정.
# (주의: 빈 문자열 "" 은 Python 사전식 비교에서 모든 HH:MM 문자열보다 작아 항상 True 가 되므로 사용 금지)
EOD_FORCE_TIME: Optional[str] = None
DAILY_STOP_LOSS_PCT = 0.04  # 일간 손실 한도: 계좌 대비 4% 초과 시 당일 신규 진입 중단 (0.0 = 비활성화)
# 라이브 실거래 권장 설정:
#   초기(1~2주): --risk_pct 0.005 --max_positions 4 --universe_n 30
#   안정화 후:   --risk_pct 0.01  --max_positions 6 --universe_n 30
#   ※ universe_n=20은 백테스트 UNIVERSE_TOP_N=20 (run_swing_mom_kpi.py)과 매칭

_NAME_CACHE: Dict[str, str] = {}
_NAME_CACHE_LOADED: bool = False  # 재시도 방지 sentinel

# ── 실시간 수급 필터 (외국인/기관 가집계 — 라이브 전용) ─────────────────────────
_KIS_API_V2 = None


def _get_kis_api_v2():
    global _KIS_API_V2
    if _KIS_API_V2 is not None:
        return _KIS_API_V2
    try:
        from api.kis_api_v2 import KisApiV2  # type: ignore
        from config.api_keys import get_kis_keys  # type: ignore
        keys = get_kis_keys()
        if keys.get("app_key") and keys.get("app_secret"):
            _KIS_API_V2 = KisApiV2(
                app_key=keys["app_key"],
                app_secret=keys["app_secret"],
                account_no=keys.get("account_no", ""),
                is_mock=keys.get("is_mock", True),
            )
    except Exception as _e:
        logger.warning(f"[수급필터] KisApiV2 초기화 실패: {_e}")
    return _KIS_API_V2


def _check_investor_flow(ticker: str) -> bool:
    """외국인/기관 장중 가집계 수급 체크 (라이브 전용 필터).

    Returns:
        True  — 진입 허용 (외국인 OR 기관 중 하나 이상 순매수, 또는 API 실패 시 fail-open)
        False — 진입 차단 (외국인 AND 기관 모두 순매도)
    """
    if IS_MOCK:
        return True  # 모의투자: 가집계 API 미지원 → 필터 비활성
    api = _get_kis_api_v2()
    if api is None:
        return True  # 초기화 실패 → fail-open
    try:
        flow = api.get_investor_trend_estimate(ticker)
        if flow.get("stale"):
            return True  # API 조회 실패 → fail-open
        frgn = int(flow.get("foreign_net_buy", 0) or 0)
        inst = int(flow.get("institution_net_buy", 0) or 0)
        if frgn >= 0 and inst >= 0:
            logger.info(f"  [수급필터] {ticker} ✓ 외국인={frgn:+,} 기관={inst:+,}")
            return True
        logger.info(
            f"  [수급필터] {ticker} ✗ 차단 — 외국인={frgn:+,} 기관={inst:+,} (순매도 감지)"
        )
        return False
    except Exception as _e:
        logger.debug(f"  [수급필터] {ticker} 오류 → fail-open: {_e}")
        return True
try:
    _journal = TradingJournal()
except Exception:
    _journal = None  # scan-only 모드에서는 저널 불필요


def _load_name_cache() -> None:
    """KOSPI+KOSDAQ 전체 종목명 1회 일괄 로드 (ticker별 개별 조회보다 안정적)."""
    global _NAME_CACHE_LOADED
    if _NAME_CACHE_LOADED:
        return
    _NAME_CACHE_LOADED = True  # 실패해도 재시도 없음 (개별 fallback 사용)

    # 1) pykrx 시도 (장 중 가장 신뢰도 높음)
    try:
        import datetime
        from pykrx import stock as krx
        today = datetime.date.today().strftime("%Y%m%d")
        pykrx_log = logging.getLogger()
        prev = pykrx_log.disabled
        pykrx_log.disabled = True
        try:
            for market in ("KOSPI", "KOSDAQ"):
                tickers = krx.get_market_ticker_list(today, market=market)
                for t in tickers:
                    name = krx.get_market_ticker_name(t)
                    if name and name != t:
                        _NAME_CACHE[t] = name
        finally:
            pykrx_log.disabled = prev
        if _NAME_CACHE:
            logger.info(f"[이름 캐시] pykrx {len(_NAME_CACHE)}개 로드 완료")
            return
    except Exception as e:
        logger.warning(f"[이름 캐시] pykrx 실패 — FDR fallback 시도: {e}")

    # 2) FinanceDataReader 폴백 (장 외 시간에도 안정적)
    try:
        import FinanceDataReader as fdr
        for market in ("KOSPI", "KOSDAQ"):
            df = fdr.StockListing(market)
            if df is not None and not df.empty and {"Code", "Name"}.issubset(df.columns):
                for row in df[["Code", "Name"]].itertuples(index=False):
                    code = str(row.Code).zfill(6)
                    name = str(row.Name)
                    if name and name != code:
                        _NAME_CACHE[code] = name
        logger.info(f"[이름 캐시] FDR {len(_NAME_CACHE)}개 로드 완료")
    except Exception as e:
        logger.warning(f"[이름 캐시] FDR 실패: {e}")


def _get_stock_name(ticker: str) -> str:
    # 1순위: config.stock_names 공유 캐시 (FDR → pykrx 순으로 로드됨)
    try:
        from config.stock_names import get_name as _cfg_get_name
        name = _cfg_get_name(ticker)
        if name and name != ticker:
            _NAME_CACHE[ticker] = name
            return name
    except Exception:
        pass
    # 2순위: 로컬 캐시
    if ticker in _NAME_CACHE:
        return _NAME_CACHE[ticker]
    if not _NAME_CACHE_LOADED:
        _load_name_cache()
        if ticker in _NAME_CACHE:
            return _NAME_CACHE[ticker]
    return ticker


# ── 포지션 ────────────────────────────────────────────────────────────────────

@dataclass
class SwingPosition:
    ticker:        str
    entry_price:   float
    sl_price:      float
    tp1_price:     float   # 1차 목표 (1%)
    tp2_price:     float   # 2차 목표 (3%)
    qty_total:     int
    qty_remaining: int
    entry_ts:      str
    entry_bar_idx: int
    status:        str = "OPEN"   # OPEN / LEG1_DONE / CLOSED
    leg1_done:     bool = False
    leg1_done_bar_idx: int = -1
    leg2_peak:     float = 0.0
    leg2_fixed_qty: int = 0
    leg2_trail_qty: int = 0
    bars_held:     int = 0
    realized_pnl:  float = 0.0
    name:          str = ""
    addon_qty:     int   = 0      # 분할매수 2차 수량 (0이면 비활성)
    addon_done:    bool  = False   # 2차 매수 완료 여부
    addon_count:   int   = 0
    addon_last_bar_idx: int = -1
    sell_blocked_until: float = 0.0  # 매도 재시도 차단 타임스탬프 (epoch seconds)
    was_negative:  bool  = False   # 진입 후 한 번이라도 마이너스 구간 경험 여부
    sell_fail_count: int  = 0      # pending_order+잔고불일치 연속 실패 횟수 (3회 초과 시 강제 CLOSED)
    tp1_executed:   bool  = False  # TP1 분할매도가 실제로 실행됐는지 (TP1 스킵 시 False)


@dataclass
class TradingState:
    positions:     Dict[str, SwingPosition] = field(default_factory=dict)
    daily_pnl:     float = 0.0
    initial_equity: float = 0.0
    signal_count:  int = 0
    entry_closed:  bool = False
    _equity_is_fallback: bool = False
    account_value_unknown: bool = False
    # unknown 포지션(브로커에만 존재, 봇이 관리하지 않는 잔고) 감지 시 세팅.
    # account_value_unknown 과 달리 계좌가치 재조회가 성공해도 자동 해제되지 않음 —
    # 운영자가 수동 reconcile 후 state 파일 편집 또는 프로세스 재시작으로만 초기화.
    entry_blocked_unknown_position: bool = False
    candidates:    list = field(default_factory=list)
    history:       list = field(default_factory=list)  # 청산 완료 거래 이력
    peak_equity:   float = 0.0  # [RISK: cumDD] 누적 고점 자산가치
    # Codex US-02: 같은 종목 일중 중복 진입 방지 (옵션 활성화 시 사용).
    daily_entered: set  = field(default_factory=set)
    daily_entered_date: str = ""  # ISO date — 날짜 바뀌면 자동 reset
    # 연속 SL 쿨다운: N연속 SL 시 신규 진입을 P분 차단 (2026-04-27 추가)
    consecutive_sl_count: int = 0
    sl_cooldown_until:    float = 0.0  # epoch seconds


# ── 포지션 영속화 ─────────────────────────────────────────────────────────────
# 스윙 모드에서 프로세스 재시작 시 오버나잇 보유 포지션을 복원하기 위한 JSON 저장.

_STATE_PATH = os.path.join(_ROOT, "state", "swing_mom_state.json")
_CANDIDATES_PATH = os.path.join(_ROOT, "state", "swing_mom_candidates.json")


def _save_state(state: "TradingState") -> None:
    """state.positions 와 daily_pnl 을 JSON 으로 저장."""
    import json
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        payload = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "saved_date": date.today().isoformat(),
            "daily_pnl": state.daily_pnl,
            "signal_count": state.signal_count,
            # Codex US-02: 같은 종목 일중 재진입 차단 set 영속화 (날짜 동반 저장).
            "daily_entered": sorted(state.daily_entered),
            "daily_entered_date": state.daily_entered_date,
            "history": state.history[-200:],  # 최근 200건만 보존
            "positions": {
                tk: {
                    "ticker": p.ticker,
                    "entry_price": p.entry_price,
                    "sl_price": p.sl_price,
                    "tp1_price": p.tp1_price,
                    "tp2_price": p.tp2_price,
                    "qty_total": p.qty_total,
                    "qty_remaining": p.qty_remaining,
                    "entry_ts": p.entry_ts,
                    "entry_bar_idx": p.entry_bar_idx,
                    "status": p.status,
                    "leg1_done": p.leg1_done,
                    "leg1_done_bar_idx": p.leg1_done_bar_idx,
                    "leg2_peak": p.leg2_peak,
                    "leg2_fixed_qty": p.leg2_fixed_qty,
                    "leg2_trail_qty": p.leg2_trail_qty,
                    "bars_held": p.bars_held,
                    "realized_pnl": p.realized_pnl,
                    "addon_qty": p.addon_qty,
                    "addon_done": p.addon_done,
                    "addon_count": p.addon_count,
                    "addon_last_bar_idx": p.addon_last_bar_idx,
                    "sell_blocked_until": p.sell_blocked_until,
                    "was_negative": p.was_negative,
                    "sell_fail_count": p.sell_fail_count,
                    "tp1_executed": p.tp1_executed,
                }
                for tk, p in state.positions.items()
                if p.status != "CLOSED" and p.qty_remaining > 0
            },
        }
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _STATE_PATH)
    except Exception as e:
        logger.warning(f"state 저장 실패: {e}")


def _load_state() -> Optional[dict]:
    """저장된 state payload 를 로드. 파일 없거나 파싱 실패 시 None."""
    import json
    if not os.path.exists(_STATE_PATH):
        return None
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"state 로드 실패: {e}")
        return None


def _save_candidates(candidates: list) -> None:
    """매수 고려 종목을 별도 파일에 원자적으로 저장 (대시보드 전용)."""
    import json
    try:
        os.makedirs(os.path.dirname(_CANDIDATES_PATH), exist_ok=True)
        payload = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "candidates": candidates,
        }
        tmp = _CANDIDATES_PATH + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _CANDIDATES_PATH)
    except Exception as e:
        logger.debug(f"candidates 저장 실패 (무시): {e}")


def _restore_positions(state: "TradingState", payload: dict) -> int:
    """payload 에서 SwingPosition 객체 복원. 복원 개수 반환.

    주의: 당일 daily_pnl 은 같은 날일 때만 복원. 날짜 바뀌면 0 으로 리셋.
    """
    pos_dict = payload.get("positions", {}) or {}
    restored = 0
    for tk, d in pos_dict.items():
        try:
            pos = SwingPosition(
                ticker=d["ticker"],
                entry_price=float(d["entry_price"]),
                sl_price=float(d["sl_price"]),
                tp1_price=float(d["tp1_price"]) if d.get("tp1_price") is not None else 0.0,
                tp2_price=float(d["tp2_price"]) if d.get("tp2_price") is not None else 0.0,
                qty_total=int(d["qty_total"]),
                qty_remaining=int(d["qty_remaining"]),
                entry_ts=d["entry_ts"],
                entry_bar_idx=int(d.get("entry_bar_idx", 0)),
                status=d.get("status", "OPEN"),
                leg1_done=bool(d.get("leg1_done", False)),
                leg1_done_bar_idx=int(d.get("leg1_done_bar_idx", -1)),
                leg2_peak=float(d.get("leg2_peak", 0.0)),
                leg2_fixed_qty=int(d.get("leg2_fixed_qty", 0)),
                leg2_trail_qty=int(d.get("leg2_trail_qty", 0)),
                bars_held=int(d.get("bars_held", 0)),
                realized_pnl=float(d.get("realized_pnl", 0.0)),
                addon_qty=int(d.get("addon_qty", 0)),
                addon_done=bool(d.get("addon_done", False)),
                addon_count=int(d.get("addon_count", 0)),
                addon_last_bar_idx=int(d.get("addon_last_bar_idx", -1)),
                sell_blocked_until=float(d.get("sell_blocked_until", 0.0)),
                was_negative=bool(d.get("was_negative", False)),
                sell_fail_count=int(d.get("sell_fail_count", 0)),
                tp1_executed=bool(d.get("tp1_executed", False)),
            )
            if pos.qty_remaining > 0 and pos.status != "CLOSED":
                state.positions[tk] = pos
                restored += 1
        except Exception as e:
            logger.warning(f"포지션 복원 실패 {tk}: {e}")
    # daily_pnl / history 는 같은 날 재시작일 때만 복원
    today_iso = date.today().isoformat()
    if payload.get("saved_date") == today_iso:
        state.daily_pnl    = float(payload.get("daily_pnl", 0.0))
        state.signal_count = int(payload.get("signal_count", 0))
        state.history      = list(payload.get("history", []))
    # Codex US-02: daily_entered 는 saved_date / daily_entered_date 둘 다
    # 오늘과 일치할 때만 복원. 날짜 바뀌면 자동 reset.
    saved_dt_date = payload.get("daily_entered_date") or payload.get("saved_date")
    if saved_dt_date == today_iso:
        state.daily_entered = set(payload.get("daily_entered", []) or [])
        state.daily_entered_date = today_iso
    else:
        state.daily_entered = set()
        state.daily_entered_date = today_iso
    return restored


def _reconcile_with_broker(state: "TradingState", kis_client) -> dict:
    """KIS 계좌 잔고와 state.positions 대조.

    Returns:
        {
            "aligned":   [ticker, ...],   # 파일 ∩ 브로커, qty 일치
            "mismatch":  [(ticker, file_qty, broker_qty), ...],  # qty 불일치
            "orphaned":  [ticker, ...],   # 파일에 있지만 브로커에 없음 (외부 매도)
            "unknown":   [(ticker, qty), ...],  # 브로커에 있지만 파일에 없음 (외부 매수 또는 이전 run)
        }
    """
    result = {"aligned": [], "mismatch": [], "orphaned": [], "unknown": []}
    try:
        holdings = kis_client.get_balance() or []
    except Exception as e:
        logger.warning(f"브로커 잔고 조회 실패 — reconcile 스킵: {e}")
        return result

    broker_map: Dict[str, int] = {}
    for row in holdings:
        raw_code = str(row.get("pdno") or row.get("pdno_cd") or "").strip()
        if not raw_code:
            continue
        code = raw_code.zfill(6)
        try:
            qty = int(float(row.get("hldg_qty") or 0))
        except Exception:
            qty = 0
        if qty > 0:
            broker_map[code] = qty

    # 파일 ↔ 브로커 비교
    file_tickers = set(state.positions.keys())
    broker_tickers = set(broker_map.keys())

    for tk in file_tickers & broker_tickers:
        file_qty = state.positions[tk].qty_remaining
        brk_qty  = broker_map[tk]
        if file_qty == brk_qty:
            result["aligned"].append(tk)
        else:
            result["mismatch"].append((tk, file_qty, brk_qty))
            # 브로커 기준으로 qty 보정 (신뢰 기준 = 실제 잔고)
            state.positions[tk].qty_remaining = brk_qty
            if brk_qty == 0:
                state.positions[tk].status = "CLOSED"

    # 파일에만 있고 브로커에 없음 → 외부 청산 추정
    for tk in file_tickers - broker_tickers:
        result["orphaned"].append(tk)
        state.positions[tk].status = "CLOSED"
        state.positions[tk].qty_remaining = 0

    # 브로커에만 있고 파일에 없음 → 외부 매수 또는 이전 run 흔적 (자동 restore 안 함, 로깅만)
    for tk in broker_tickers - file_tickers:
        result["unknown"].append((tk, broker_map[tk]))

    # CLOSED 된 포지션 정리
    state.positions = {
        tk: p for tk, p in state.positions.items()
        if p.status != "CLOSED" and p.qty_remaining > 0
    }
    return result


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def _is_eod_force(now_hhmm: str) -> bool:
    """당일 강제 청산 시간 도달 여부.
    EOD_FORCE_TIME 이 None 또는 빈 문자열이면 스윙 모드로 간주 → 항상 False.
    """
    if not EOD_FORCE_TIME:
        return False
    return now_hhmm >= EOD_FORCE_TIME


def _ensure_leg2_allocation(pos: SwingPosition, params: dict) -> None:
    """Rebuild the fixed/trailing Leg2 split from the current remaining quantity when needed."""
    if not pos.leg1_done or pos.qty_remaining <= 0:
        pos.leg2_fixed_qty = 0
        pos.leg2_trail_qty = 0
        return

    if pos.leg2_fixed_qty + pos.leg2_trail_qty != pos.qty_remaining:
        trail_pct = float(params.get("tp2_trail_pct", 0.0) or 0.0)
        trail_ratio = float(params.get("tp2_trail_ratio", 0.0) or 0.0) if trail_pct > 0 else 0.0
        trail_qty = 0
        if trail_ratio > 0:
            trail_qty = min(int(pos.qty_total * trail_ratio), pos.qty_remaining)
        pos.leg2_trail_qty = trail_qty
        pos.leg2_fixed_qty = max(0, pos.qty_remaining - trail_qty)

    if pos.leg2_peak <= 0:
        pos.leg2_peak = pos.entry_price


# KRX 정규장 (09:00~15:30 = 390분 = 78 × 5분봉 / 일)
_KRX_RTH_START = datetime.strptime("09:00", "%H:%M").time()
_KRX_RTH_END   = datetime.strptime("15:30", "%H:%M").time()

# KRX 법정 공휴일/임시공휴일 캐시 (pykrx 로 지연 로딩)
_KRX_HOLIDAY_CACHE: Optional[set] = None


def _load_krx_holidays() -> set:
    """최근 2년 + 다음 1년 범위의 KRX 휴장일을 pykrx 로 계산해 캐싱.

    구현: KOSPI 지수(1001) 의 일봉이 존재하지 않는 주중 날짜 = 휴장일.
    pykrx 가 없거나 호출 실패 시 빈 set 반환 → 월~금 기본 로직 유지.
    """
    global _KRX_HOLIDAY_CACHE
    if _KRX_HOLIDAY_CACHE is not None:
        return _KRX_HOLIDAY_CACHE
    holidays: set = set()
    try:
        from pykrx import stock as _krx  # type: ignore
        from datetime import timedelta as _td
        today_d = date.today()
        start_d = today_d - _td(days=730)
        end_d   = today_d + _td(days=365)
        # pykrx 는 한 번의 range 쿼리로 거래일만 반환함
        df = _krx.get_index_ohlcv_by_date(
            start_d.strftime("%Y%m%d"), end_d.strftime("%Y%m%d"), "1001"
        )
        if df is not None and len(df) > 0:
            biz_days = {d.date() for d in df.index.to_pydatetime()}
            cur = start_d
            while cur <= end_d:
                if cur.weekday() < 5 and cur not in biz_days:
                    holidays.add(cur)
                cur += _td(days=1)
    except Exception as e:
        logger.debug(f"pykrx 휴장일 로드 실패 — 월~금 기본 로직 사용: {e}")
    _KRX_HOLIDAY_CACHE = holidays
    if holidays:
        logger.info(f"KRX 휴장일 캐시 로드: {len(holidays)}일")
    return _KRX_HOLIDAY_CACHE


def _rth_bars_between(entry_ts: str, now_dt: Optional[datetime] = None) -> int:
    """entry_ts 부터 now_dt 까지 KRX 정규장(09:00~15:30) 5분봉 누적 개수.

    벽시계 아닌 장중 시간만 카운트 — 장 마감/야간/주말/휴일 제외.
    월~금 중 KRX 법정 공휴일(pykrx 로 조회) 은 추가로 제외.
    """
    from datetime import timedelta
    if not entry_ts:
        return 0
    try:
        entry_dt = datetime.strptime(str(entry_ts)[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return 0
    now_dt = now_dt or datetime.now()
    if now_dt <= entry_dt:
        return 0

    holidays = _load_krx_holidays()
    total_rth_min = 0
    cur_date = entry_dt.date()
    end_date = now_dt.date()

    while cur_date <= end_date:
        is_biz = cur_date.weekday() < 5 and cur_date not in holidays
        if is_biz:
            day_start = datetime.combine(cur_date, _KRX_RTH_START)
            day_end   = datetime.combine(cur_date, _KRX_RTH_END)
            seg_start = max(entry_dt, day_start)
            seg_end   = min(now_dt,   day_end)
            if seg_end > seg_start:
                total_rth_min += int((seg_end - seg_start).total_seconds() / 60)
        cur_date += timedelta(days=1)

    return total_rth_min // 5


def _collect_tickers(data_dir: str) -> List[str]:
    return sorted(
        fn.replace("_5m.csv", "")
        for fn in os.listdir(data_dir)
        if fn.endswith("_5m.csv")
    )


def _load_daily_turnover_cache(tickers: List[str], daily_dir: str) -> Dict[str, Dict[str, float]]:
    """일봉 CSV → {ticker: {date_str: close*volume}} 매핑 일괄 로드."""
    cache: Dict[str, Dict[str, float]] = {}
    for t in tickers:
        fp = os.path.join(daily_dir, f"{t}_1d.csv")
        if not os.path.exists(fp):
            continue
        try:
            df = pl.read_csv(fp).sort("date")
            dates  = [str(d)[:10] for d in df["date"].cast(pl.Utf8).to_list()]
            closes = df["close"].cast(pl.Float64).to_list()
            volumes = df["volume"].cast(pl.Float64).to_list()
            cache[t] = {
                d: float(c) * float(v)
                for d, c, v in zip(dates, closes, volumes)
                if c and v
            }
        except Exception:
            pass
    return cache


def _top_n_by_volume(tickers: List[str], daily_dir: str, n: int = 100) -> List[str]:
    """라이브 트레이더 거래대금 상위 N 유니버스.

    utils.liquidity_universe.build_liquidity_universe 를 통한 통합 SSOT 호출.
    1d CSV 의 가장 최신 5거래일 평균 close*volume 을 turnover 로 사용.
    """
    cache = _load_daily_turnover_cache(tickers, daily_dir)
    if not cache:
        logger.info(f"거래대금 Top {n} 유니버스 (0종목): []")
        return []

    # 기존 동작 보존: tail(5) 평균 — 가장 최신 5개 거래일.
    # 달력일이 아닌 "데이터에 존재하는 최신 5거래일" 을 사용해야 하므로
    # provider 를 ticker 별로 캐싱한 정렬 인덱스 기반으로 매핑.
    sorted_dates: Dict[str, List[str]] = {
        t: sorted(d.keys(), reverse=True)[:5] for t, d in cache.items()
    }

    # asof: 모든 ticker 가운데 가장 최신 거래일.
    all_recent = [dates[0] for dates in sorted_dates.values() if dates]
    if not all_recent:
        return []
    from datetime import date as _date_cls
    asof = _date_cls.fromisoformat(max(all_recent))

    # provider: 해당 ticker 의 5거래일 셋트에 들어있는 날만 turnover 반환,
    # 그 외 날짜는 0 → 평균 계산에서 제외.
    def _live_provider(ticker: str, d) -> float:
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        if date_str in sorted_dates.get(ticker, []):
            return cache.get(ticker, {}).get(date_str, 0.0)
        return 0.0

    # lookback 은 충분히 크게 (30일) 잡아 최근 5거래일이 모두 포함되도록.
    selected = build_liquidity_universe(
        tickers=list(cache.keys()),
        turnover_provider=_live_provider,
        asof_date=asof,
        lookback=30,
        n=n,
    )
    logger.info(f"거래대금 Top {n} 유니버스 ({len(selected)}종목): {selected}")
    return selected


def _liq_scores(tickers: List[str], daily_dir: str) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for t in tickers:
        fp = os.path.join(daily_dir, f"{t}_1d.csv")
        if not os.path.exists(fp):
            continue
        try:
            df = pl.read_csv(fp).sort("date").tail(10)
            closes  = df["close"].cast(pl.Float64).to_list()
            volumes = df["volume"].cast(pl.Float64).to_list()
            vals = [c * v for c, v in zip(closes, volumes) if c and v]
            scores[t] = sum(vals[-5:]) / len(vals[-5:]) if vals else 0.0
        except Exception:
            pass
    return scores


# ── 수동 블랙리스트 ─────────────────────────────────────────────────────────
# 영구적으로 제외할 종목 코드 (관리종목 지정 해제 후에도 위험하다고 판단한 종목 등)
MANUAL_BLACKLIST: set[str] = set()

# FID_TRGT_EXLS_CLS_CODE 각 자리 의미 (KIS OpenAPI FHPST01710000)
# 1:관리종목  2:투자경고  3:투자주의  4:우선주  5:투자위험예고
# 6:투자위험  7:거래정지  8:단기과열  9~10: reserved
_KIS_EXLS_CODE = "1110111100"  # 관리·투자경고·투자주의·투자위험예고·투자위험·거래정지·단기과열 제외

# ETF/ETN 종목명 키워드 (거래대금 유니버스에서 제외)
_ETF_ETN_KEYWORDS = (
    "KODEX", "TIGER", "KOSEF", "KBSTAR", "ARIRANG", "HANARO", "SOL", "PLUS",
    "ACE ", "TIMEFOLIO", "WOORI", "BNK", "히어로즈",
    "ETN", "TRUE", "QV ", "신한", "미래에셋", "삼성레버리지", "인버스",
)


def _is_etf_etn(name: str) -> bool:
    """종목명 기반 ETF/ETN 판별."""
    if not name:
        return False
    upper = name.upper().strip()
    for kw in _ETF_ETN_KEYWORDS:
        if kw.upper() in upper:
            return True
    return False


def _is_bad_security(name: str) -> bool:
    """종목명 기반 불량종목(우선주·스팩·리츠) 판별.
    우선주는 KIS EXLS 4번 자리가 항상 보장되지 않으므로 종목명으로도 한 번 더 거른다.
    """
    if not name:
        return False
    s = name.strip()
    # 우선주: 끝이 "우", "우B", "2우B", "3우B" 패턴
    if s.endswith("우") or s.endswith("우B") or s.endswith("2우B") or s.endswith("3우B"):
        return True
    # 스팩 (SPAC) — 합병 전까지 주가 1좌당 2,000원 고정 흐름
    if "스팩" in s or "SPAC" in s.upper():
        return True
    # 리츠 — 부동산투자회사, 변동성 패턴이 일반 주식과 다름
    if s.endswith("리츠") or "리츠 " in s:
        return True
    return False


def _fetch_volume_rank(client, n: int = 100):
    """KIS 실시간 거래대금 순위 조회 → (tickers, liq_scores) 반환.
    ETF/ETN은 자동 제외. 실패 시 ([], {}) 반환 — 호출자가 기존 값 유지.

    KIS volume-rank API는 호출당 최대 30종목만 반환하므로,
    n > 30 인 경우 KOSPI(0001)+KOSDAQ(1001) 분리 호출 후 거래대금순으로 병합한다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = client._headers("FHPST01710000")

    def _page(market_code: str) -> list:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE":  "20171",
            "FID_INPUT_ISCD":         market_code,
            "FID_DIV_CLS_CODE":       "0",
            "FID_BLNG_CLS_CODE":      "0",
            "FID_TRGT_CLS_CODE":      "111111111",
            "FID_TRGT_EXLS_CLS_CODE": _KIS_EXLS_CODE,
            "FID_INPUT_PRICE_1":      "",
            "FID_INPUT_PRICE_2":      "",
            "FID_VOL_CNT":            "",
            "FID_INPUT_DATE_1":       "",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        return resp.json().get("output", []) or []

    def _amt(row: dict) -> int:
        try:
            return int(str(row.get("acml_tr_pbmn", 0)).replace(",", ""))
        except Exception:
            return 0

    try:
        if n <= 30:
            rows = _page("0000")
        else:
            kospi  = _page("0001")
            kosdaq = _page("1001")
            merged: Dict[str, dict] = {}
            for row in list(kospi) + list(kosdaq):
                code = (row.get("mksc_shrn_iscd") or "").strip()
                if code and code not in merged:
                    merged[code] = row
            rows = sorted(merged.values(), key=_amt, reverse=True)
        tickers_out: List[str] = []
        scores_out:  Dict[str, float] = {}
        skipped_etf: List[str] = []
        skipped_price_floor: List[str] = []
        skipped_bad: List[str] = []
        skipped_stat: List[str] = []
        rank_idx = 0
        for row in rows:
            code = (row.get("mksc_shrn_iscd") or "").strip()
            name = (row.get("hts_kor_isnm") or "").strip()
            if not (code and len(code) == 6 and code.isdigit()):
                continue
            price_reason = classify_price_floor([row.get("stck_prpr")])
            if price_reason:
                skipped_price_floor.append(f"{code}({name})")
                continue
            # ETF/ETN 제외
            if _is_etf_etn(name):
                skipped_etf.append(f"{code}({name})")
                continue
            # 불량종목(우선주·스팩·리츠) 제외
            if _is_bad_security(name):
                skipped_bad.append(f"{code}({name})")
                continue
            # 수동 블랙리스트 제외
            if code in MANUAL_BLACKLIST:
                skipped_bad.append(f"{code}({name})[BL]")
                continue
            # API 응답에 종목상태코드가 있는 경우 2차 필터 (정상=00 외 모두 제외)
            stat = (row.get("iscd_stat_cls_code") or "00").strip()
            if stat not in ("00", ""):
                skipped_stat.append(f"{code}({name})[stat={stat}]")
                continue
            tickers_out.append(code)
            scores_out[code] = 1.0 - rank_idx / max(n - 1, 1)
            rank_idx += 1
            if len(tickers_out) >= n:
                break
        if tickers_out:
            logger.info(
                f"거래대금 순위: {len(rows)}행 수신 → Top{len(tickers_out)} 선택 "
                f"(ETF/ETN {len(skipped_etf)}개 | 동전주 {len(skipped_price_floor)}개 | "
                f"불량종목 {len(skipped_bad)}개 | 상태이상 {len(skipped_stat)}개 제외)"
            )
            if skipped_bad:
                logger.debug(f"제외된 불량종목: {skipped_bad[:10]}{'...' if len(skipped_bad)>10 else ''}")
            if skipped_stat:
                logger.debug(f"제외된 상태이상: {skipped_stat[:10]}{'...' if len(skipped_stat)>10 else ''}")
            if skipped_etf:
                logger.debug(f"제외된 ETF/ETN: {skipped_etf[:10]}{'...' if len(skipped_etf)>10 else ''}")
            if skipped_price_floor:
                logger.debug(f"제외된 동전주: {skipped_price_floor[:10]}{'...' if len(skipped_price_floor)>10 else ''}")
            return tickers_out, scores_out
    except Exception as e:
        logger.warning(f"거래대금 순위 조회 실패: {e}")
    return [], {}


def _backfill_index_hist(
    kis_client, data_dir: str, index_ticker: str = "069500", days: int = 10
) -> bool:
    """069500 인덱스 5분봉을 KIS API로 최대한 수집하여 CSV에 저장.

    KIS 분봉 API(FHKST03010200)는 당일 데이터만 반환하므로,
    이 함수는 오늘 장 시작(09:00)~현재 시각까지의 1분봉을 최대한 수집한다.
    재시작 시 이전 구간 데이터를 복구하는 효과가 있다.

    Returns True if data is sufficient (>=30 bars in CSV).
    """
    csv_path = os.path.join(data_dir, f"{index_ticker}_5m.csv")
    today_str = date.today().strftime("%Y-%m-%d")

    if kis_client is None:
        logger.warning(f"인덱스({index_ticker}) KIS 미연결 — 백필 불가")
        return False

    logger.info(f"인덱스({index_ticker}) 히스토리 백필 시작 (당일 전체)...")

    # _fetch_kis_5m 재사용: 오늘 전체 1분봉 수집
    idx_bars = _fetch_kis_5m(kis_client, index_ticker, max_pages=10)
    if not idx_bars:
        logger.warning(f"인덱스({index_ticker}) 백필 실패 — API 응답 없음")
        return False

    df_new = pl.DataFrame(idx_bars).sort("datetime").unique("datetime")
    # volume=0인 가짜 봉 제거 (장외 시간 데이터)
    if "volume" in df_new.columns:
        df_new = df_new.filter(pl.col("volume").cast(pl.Int64) > 0)

    if len(df_new) < 3:
        logger.warning(f"인덱스({index_ticker}) 유효 봉 {len(df_new)}개 — 백필 부족")
        return False

    # 기존 CSV와 병합 (오늘+과거 모두 유지)
    try:
        if os.path.exists(csv_path):
            df_old = pl.read_csv(csv_path)
            # 기존에서 volume=0 제거
            if "volume" in df_old.columns and len(df_old) > 0:
                df_old = df_old.filter(pl.col("volume").cast(pl.Int64, strict=False) > 0)
            if len(df_old) > 0:
                df_merged = pl.concat([df_old, df_new]).sort("datetime").unique("datetime")
            else:
                df_merged = df_new
        else:
            df_merged = df_new
    except Exception:
        df_merged = df_new

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    df_merged.write_csv(csv_path)
    logger.info(f"인덱스({index_ticker}) 백필 완료: CSV {len(df_merged)}행 (오늘 {len(df_new)}봉)")
    return len(df_merged) >= 30


def _load_sector_map(data_dir: str) -> Dict[str, str]:
    csv_path = os.path.join(os.path.dirname(data_dir), "sector_classifications.csv")
    if not os.path.exists(csv_path):
        return {}
    try:
        df = pl.read_csv(csv_path, infer_schema_length=200)
        return {str(r["ticker"]).zfill(6): str(r["sector_name"]) for r in df.to_dicts()}
    except Exception:
        return {}


# ── KIS 5분봉 조회 ─────────────────────────────────────────────────────────────

def _fetch_kis_5m(client, ticker: str, max_pages: int = 6) -> List[dict]:
    """KIS 당일 1분봉 전체 조회 (현재 시각부터 역순 페이지네이션)."""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    today_str = datetime.now().strftime("%Y%m%d")
    all_bars = {}  # datetime -> bar (중복 제거)

    # 현재 시각부터 역순으로 조회 (페이지당 최대 30봉)
    base_time = datetime.now().strftime("%H%M%S")

    for page in range(max_pages):
        headers = client._headers("FHKST03010200")
        params = {
            "fid_etc_cls_code":       "",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd":         ticker,
            "fid_input_hour_1":       base_time,
            "fid_pw_data_incu_yn":    "Y",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            data = resp.json()
            rows = data.get("output2", [])
            if not rows:
                break

            earliest_tm = None
            for row in rows:
                dt_str = row.get("stck_bsop_date", "")
                tm_str = row.get("stck_cntg_hour", "")
                if not dt_str or not tm_str:
                    continue
                # 오늘 데이터만 수집
                if dt_str != today_str:
                    continue
                dt_fmt = (
                    f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} "
                    f"{tm_str[:2]}:{tm_str[2:4]}:00"
                )
                all_bars[dt_fmt] = {
                    "datetime": dt_fmt,
                    "open":   float(row.get("stck_oprc", 0) or 0),
                    "high":   float(row.get("stck_hgpr", 0) or 0),
                    "low":    float(row.get("stck_lwpr", 0) or 0),
                    "close":  float(row.get("stck_prpr", 0) or 0),
                    "volume": int(row.get("cntg_vol", 0) or 0),
                }
                if earliest_tm is None or tm_str < earliest_tm:
                    earliest_tm = tm_str

            # 다음 페이지: 가장 이른 시각부터 역순 조회
            if earliest_tm is None or earliest_tm <= "090000":
                break
            base_time = earliest_tm
            time.sleep(0.08)
        except Exception as e:
            logger.debug(f"{ticker} 5m 조회 실패 (page {page}): {e}")
            break

    return sorted(all_bars.values(), key=lambda x: x["datetime"])


def _fetch_one(args):
    client, ticker = args
    bars = _fetch_kis_5m(client, ticker)
    time.sleep(0.12)
    return ticker, bars


def _filter_today_until_bar(
    df: pl.DataFrame,
    today_str: str,
    current_hhmm: Optional[str] = None,
) -> pl.DataFrame:
    """Keep only today's bars that are not later than current_hhmm."""
    if df is None or len(df) == 0 or "datetime" not in df.columns:
        return df

    dt_col = pl.col("datetime").cast(pl.Utf8)
    out = df.filter(dt_col.str.starts_with(today_str))
    if current_hhmm:
        cutoff = f"{today_str} {current_hhmm}:59"
        out = out.filter(dt_col <= cutoff)
    return out


def _load_today_5m(
    tickers: List[str],
    data_dir: str,
    today_str: str,
    kis_client=None,
    current_hhmm: Optional[str] = None,
) -> Dict[str, pl.DataFrame]:
    dfs: Dict[str, pl.DataFrame] = {}
    if kis_client is not None and tickers:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_fetch_one, (kis_client, t)): t for t in tickers}
            for fut in as_completed(futures):
                try:
                    ticker, bars = fut.result()
                    if len(bars) >= 3:
                        df_raw = pl.DataFrame(bars)
                        df_5m = _filter_today_until_bar(
                            _resample_to_5m(df_raw), today_str, current_hhmm
                        )
                        if len(df_5m) >= 3:
                            dfs[ticker] = df_5m
                except Exception as e:
                    logger.debug(f"5분봉 fetch 실패: {e}")
        # 파일 폴백
        for t in tickers:
            if t not in dfs:
                fp = os.path.join(data_dir, f"{t}_5m.csv")
                if not os.path.exists(fp):
                    continue
                try:
                    df = _filter_today_until_bar(
                        pl.read_csv(fp), today_str, current_hhmm
                    )
                    if len(df) >= 3:
                        dfs[t] = df
                except Exception:
                    pass
        dfs, dropped = filter_price_floor_frames(dfs)
        if dropped:
            counts = {"below_floor": 0, "broken_floor": 0}
            for reason in dropped.values():
                counts[reason] = counts.get(reason, 0) + 1
            logger.info(
                "가격 하한 필터 적용: 제외 %d종목 (현재<1000원=%d, 1000원 하향이탈=%d)",
                len(dropped), counts.get("below_floor", 0), counts.get("broken_floor", 0),
            )
        return dfs
    # kis_client 없을 때 파일만 로드
    for t in tickers:
        fp = os.path.join(data_dir, f"{t}_5m.csv")
        if not os.path.exists(fp):
            continue
        try:
            df = _filter_today_until_bar(pl.read_csv(fp), today_str, current_hhmm)
            if len(df) >= 3:
                dfs[t] = df
        except Exception:
            pass
    dfs, dropped = filter_price_floor_frames(dfs)
    if dropped:
        counts = {"below_floor": 0, "broken_floor": 0}
        for reason in dropped.values():
            counts[reason] = counts.get(reason, 0) + 1
        logger.info(
            "가격 하한 필터 적용: 제외 %d종목 (현재<1000원=%d, 1000원 하향이탈=%d)",
            len(dropped), counts.get("below_floor", 0), counts.get("broken_floor", 0),
        )
    return dfs



# -- resampling ----------------------------------------------------------------

def _resample_to_5m(df_1m: pl.DataFrame) -> pl.DataFrame:
    """KIS API 1min -> 5min resample."""
    df = df_1m.with_columns(
        pl.col("datetime").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S").alias("_dt")
    ).filter(pl.col("_dt").is_not_null()
    ).with_columns(pl.col("_dt").dt.truncate("5m").alias("_bar5"))
    df5 = (
        df.group_by("_bar5").agg([
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        ]).sort("_bar5")
    )
    df5 = df5.with_columns(
        pl.col("_bar5").dt.strftime("%Y-%m-%d %H:%M:%S").alias("datetime")
    ).drop("_bar5")
    # CSV 히스토리와 컬럼 순서 일치: datetime, open, high, low, close, volume
    return df5.select(["datetime", "open", "high", "low", "close", "volume"])


# ── context 빌드 ───────────────────────────────────────────────────────────────

def _resample_to_30m(df_5m: pl.DataFrame) -> pl.DataFrame:
    df = df_5m.with_columns(
        pl.col("datetime").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S").alias("_dt")
    ).filter(
        pl.col("_dt").is_not_null()
    ).with_columns(pl.col("_dt").dt.truncate("30m").alias("_bar30"))
    df30 = (
        df.group_by("_bar30").agg([
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        ]).sort("_bar30")
    )
    return df30.with_columns(
        pl.col("_bar30").dt.strftime("%Y-%m-%d %H:%M:%S").alias("datetime")
    ).drop("_bar30")


def _normalize_bar_ts(ts) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = ts.strip()
        return ts or None
    return str(ts)


def _intraday_returns(df_30m: pl.DataFrame) -> Dict[str, float]:
    result: Dict[str, float] = {}
    dt_list = df_30m["datetime"].cast(pl.Utf8).to_list()
    closes  = df_30m["close"].cast(pl.Float64).to_list()
    opens   = df_30m["open"].cast(pl.Float64).to_list()
    cur_date = day_open = None
    for i, ts in enumerate(dt_list):
        ts = _normalize_bar_ts(ts)
        if ts is None or len(ts) < 16:
            continue
        d = ts[:10]
        if d != cur_date:
            cur_date = d
            day_open = opens[i] if opens[i] and opens[i] > 0 else None
        if day_open and day_open > 0 and closes[i] and closes[i] > 0:
            result[ts[:16]] = (closes[i] - day_open) / day_open
    return result


def _load_hist_5m(ticker: str, data_dir: str, today_str: str) -> Optional[pl.DataFrame]:
    """과거 데이터(오늘 제외) 로드."""
    fp = os.path.join(data_dir, f"{ticker}_5m.csv")
    if not os.path.exists(fp):
        return None
    try:
        df = pl.read_csv(fp).filter(
            pl.col("datetime").cast(pl.Utf8) < today_str + " 00:00:00"
        ).tail(HISTORY_DAYS * 78)   # 하루 약 78봉 (5분봉)
        return df if len(df) >= 30 else None
    except Exception:
        return None


def _build_context_map(
    tickers: List[str],
    today_dfs: Dict[str, pl.DataFrame],
    data_dir: str,
    liq_scores: Dict[str, float],
    sector_map: Dict[str, str],
    today_str: str,
    index_ticker: str = "069500",
):
    """과거 + 오늘 5분봉을 합쳐 context_map 빌드."""
    # 인덱스 데이터 구성 — 히스토리 + CSV 전체(오늘 포함) + 실시간
    # NOTE: 일반 종목은 _load_hist_5m (오늘 제외)을 쓰지만,
    #       인덱스는 수집 파이프라인에 없어 CSV에 과거가 부족할 수 있다.
    #       따라서 CSV 전체를 로드하고 today_dfs와 병합하여 최대한 활용.
    idx_parts: list = []
    idx_csv_path = os.path.join(data_dir, f"{index_ticker}_5m.csv")
    if os.path.exists(idx_csv_path):
        try:
            _idx_csv = pl.read_csv(idx_csv_path)
            if len(_idx_csv) >= 3:
                idx_parts.append(_idx_csv)
        except Exception:
            pass
    idx_today = today_dfs.get(index_ticker)
    if idx_today is not None:
        idx_parts.append(idx_today)

    if not idx_parts:
        logger.warning("인덱스(069500) 데이터 없음 — context 빌드 불가")
        return {}

    _num_cols = ["open", "high", "low", "close", "volume"]
    def _cast_float(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns([
            pl.col(c).cast(pl.Float64) for c in _num_cols if c in df.columns
        ])

    df_idx_5m = pl.concat([_cast_float(p) for p in idx_parts]).sort("datetime").unique("datetime")
    df_idx_30m = _resample_to_30m(df_idx_5m)

    idx_dt    = [v[:16] if v is not None else "" for v in df_idx_30m["datetime"].cast(pl.Utf8).to_list()]
    idx_c     = df_idx_30m["close"].cast(pl.Float64).to_list()
    idx_h     = df_idx_30m["high"].cast(pl.Float64).to_list()
    idx_v     = df_idx_30m["volume"].cast(pl.Float64).to_list()
    idx_rets  = _intraday_returns(df_idx_30m)

    tkr_rets: Dict[str, Dict[str, float]] = {}

    for t in tickers:
        try:
            hist = _load_hist_5m(t, data_dir, today_str)
            today = today_dfs.get(t)
            parts = [p for p in [hist, today] if p is not None]
            if not parts:
                continue
            df5 = pl.concat([_cast_float(p) for p in parts]).sort("datetime").unique("datetime")
            df30 = _resample_to_30m(df5)
            r = _intraday_returns(df30)
            if r:
                tkr_rets[t] = r
        except Exception as e:
            logger.debug("context용 30분봉 변환 실패 %s: %s", t, e)

    if not tkr_rets:
        logger.warning("tkr_rets 빈 dict — context_map 빌드 불가 (종목 히스토리 데이터 부족)")
        return {}

    try:
        ctx_map = build_context_states(
            index_30m_closes=idx_c,
            index_30m_highs=idx_h,
            index_30m_dt_list=idx_dt,
            index_30m_volumes=idx_v,
            ticker_returns_30m=tkr_rets,
            index_returns_30m=idx_rets,
            sector_map=sector_map,
            liquidity_scores=liq_scores,
            daily_ctx_map=None,
        )
        # 캐시 저장
        _save_context_cache(ctx_map, today_str)
        return ctx_map
    except Exception as e:
        logger.warning(f"context_map 빌드 실패: {e}")
        return {}


_CONTEXT_CACHE_PATH = os.path.join(_ROOT, "state", "context_map_cache.json")


def _save_context_cache(ctx_map: dict, today_str: str) -> None:
    """context_map을 디스크에 캐시 (재시작 복구용)."""
    try:
        cache = {}
        for (ticker, bar_ts), ctx in ctx_map.items():
            cache[f"{ticker}|{bar_ts}"] = {
                "m_long": ctx.m_long, "s_score": ctx.s_score,
                "d_score": ctx.d_score, "breadth_ratio": ctx.breadth_ratio,
                "liquidity_rank": ctx.liquidity_rank, "bar_ts": ctx.bar_ts,
            }
        import json
        os.makedirs(os.path.dirname(_CONTEXT_CACHE_PATH), exist_ok=True)
        with open(_CONTEXT_CACHE_PATH, "w") as f:
            json.dump({"today": today_str, "data": cache}, f)
        logger.debug(f"context_map 캐시 저장: {len(cache)}건")
    except Exception as e:
        logger.debug(f"context_map 캐시 저장 실패: {e}")


def _load_context_cache(today_str: str) -> dict:
    """디스크 캐시에서 context_map 복원 (오늘 데이터만)."""
    try:
        import json
        if not os.path.exists(_CONTEXT_CACHE_PATH):
            return {}
        with open(_CONTEXT_CACHE_PATH) as f:
            raw = json.load(f)
        if raw.get("today") != today_str:
            return {}
        from engine.context_state import ContextState
        ctx_map = {}
        for key_str, vals in raw.get("data", {}).items():
            ticker, bar_ts = key_str.split("|", 1)
            ctx_map[(ticker, bar_ts)] = ContextState(
                bar_ts=vals["bar_ts"],
                m_long=vals["m_long"], s_score=vals["s_score"],
                d_score=vals["d_score"], breadth_ratio=vals["breadth_ratio"],
                liquidity_rank=vals["liquidity_rank"],
            )
        logger.info(f"context_map 캐시 복원: {len(ctx_map)}건 (오늘 {today_str})")
        return ctx_map
    except Exception as e:
        logger.debug(f"context_map 캐시 로드 실패: {e}")
        return {}


# ── 장 종료 시 오늘 5분봉 CSV 저장 ────────────────────────────────────────────

def _save_today_5m(today_dfs: Dict[str, pl.DataFrame], data_dir: str, today_str: str) -> None:
    """오늘 수집된 5분봉 데이터를 CSV에 병합 저장 (내일 히스토리로 사용)."""
    saved = 0
    for ticker, df_today in today_dfs.items():
        if df_today is None or len(df_today) < 2:
            continue
        csv_path = os.path.join(data_dir, f"{ticker}_5m.csv")
        try:
            # 오늘 데이터만 필터 (다른 날 데이터가 섞여있을 수 있음)
            df_new = df_today.filter(
                pl.col("datetime").cast(pl.Utf8).str.starts_with(today_str)
            )
            if len(df_new) < 2:
                continue

            if os.path.exists(csv_path):
                df_old = pl.read_csv(csv_path)
                # 기존에서 오늘 데이터 제거 후 새로 추가
                df_old = df_old.filter(
                    ~pl.col("datetime").cast(pl.Utf8).str.starts_with(today_str)
                )
                df_merged = pl.concat([df_old, df_new]).sort("datetime").unique("datetime")
            else:
                df_merged = df_new.sort("datetime").unique("datetime")

            df_merged.write_csv(csv_path)
            saved += 1
        except Exception as e:
            logger.debug(f"5분봉 저장 실패 {ticker}: {e}")
    logger.info(f"오늘 5분봉 CSV 저장 완료: {saved}/{len(today_dfs)}종목")


# ── 포지션 사이즈 ─────────────────────────────────────────────────────────────

def _calc_qty(entry_price: float, sl_price: float, risk_pct: float, kis_client,
              max_position_ratio: float = 0.30,
              fallback_equity: float = 0.0) -> int:
    """계좌 잔고 기준 포지션 사이즈 계산.

    max_position_ratio: 단일 포지션이 계좌에서 차지할 수 있는 최대 비율 (기본 30%).
    fallback_equity: API 실패 시 사용할 fallback 계좌가치 (0이면 진입 중단).
    """
    account_value = kis_client.get_account_value()
    if account_value <= 0:
        if fallback_equity > 0 and IS_MOCK:
            account_value = fallback_equity
            logger.warning(f"계좌가치 조회 실패 — fallback {fallback_equity:,.0f}원으로 포지션 사이징")
        else:
            halt_msg = "🚨 [SEV1] 계좌가치 조회 실패 — 포지션 사이징 불가. 진입 중단."
            logger.error(halt_msg)
            return 0  # 0 반환 → 호출부에서 진입 스킵
    risk_per_trade = account_value * risk_pct
    risk_per_share = entry_price - sl_price
    if risk_per_share <= 0:
        logger.error(f"Invalid SL: entry={entry_price} sl={sl_price} — sizing aborted")
        return 0  # SL이 진입가 위에 있는 깨진 신호 — 주문 금지

    qty = int(risk_per_trade / risk_per_share)

    # 단일 포지션 상한: 계좌의 max_position_ratio 이내
    max_qty = max(1, int(account_value * max_position_ratio / entry_price))
    qty = min(qty, max_qty)

    if qty < int(risk_per_trade / risk_per_share):
        logger.info(f"포지션 캡 적용: 리스크 기반 {int(risk_per_trade/risk_per_share)}주 → {qty}주 "
                    f"(계좌 {account_value:,.0f}원 × {max_position_ratio:.0%})")
    if qty <= 0:
        logger.warning(f"리스크 기반 포지션 사이징 결과 0 — 진입 스킵 (entry={entry_price:.0f}, sl={sl_price:.0f})")
        return 0
    return qty


def _cap_qty_by_orderable_cash(entry_price: float, qty: int, kis_client) -> int:
    """Clamp sized quantity by actually orderable cash."""
    if qty <= 0:
        return 0
    try:
        orderable_cash = float(kis_client.get_orderable_cash() or 0.0)
    except Exception as e:
        logger.warning(f"주문가능금액 조회 실패: {e}")
        return qty

    if orderable_cash <= 0:
        return qty

    cash_limited_qty = int(orderable_cash / entry_price)
    if cash_limited_qty <= 0:
        logger.warning(
            f"주문가능금액 부족: 주문가능 {orderable_cash:,.0f}원 < 진입가 {entry_price:,.0f}원"
        )
        return 0
    if cash_limited_qty < qty:
        logger.info(
            f"주문가능금액 캡 적용: 기존 {qty}주 -> {cash_limited_qty}주 "
            f"(주문가능 {orderable_cash:,.0f}원, 진입가 {entry_price:,.0f}원)"
        )
        return cash_limited_qty
    return qty


# ── 신호 탐지 ─────────────────────────────────────────────────────────────────

def _check_signals(
    tickers: List[str],
    today_dfs: Dict[str, pl.DataFrame],
    context_map: dict,
    state: TradingState,
    current_bar_time: str,
    p: dict,
    today_str: str = "",
) -> List[dict]:
    """현재 완성 bar 기준 SWING-MOM 신호 탐지."""
    from strategies.intraday_swing_mom import check_regime_gate_swing
    from engine.context_state import get_context_for_5m_bar

    if state.entry_closed:
        return []

    # 연속 SL 쿨다운 게이트
    if state.sl_cooldown_until > time.time():
        _remain = int(state.sl_cooldown_until - time.time())
        logger.info(f"[연속SL 쿨다운] 신규 진입 차단 중 (해제까지 {_remain//60}분 {_remain%60}초)")
        return []

    # [RISK: cumDD] 누적 드로우다운 보호
    if state.peak_equity > 0:
        _cur_eq = state.initial_equity + state.daily_pnl
        cum_dd = (_cur_eq - state.peak_equity) / state.peak_equity
        if cum_dd <= -0.15:
            logger.warning("누적 DD -15%% 도달 — 강제청산 모드")
            state.entry_closed = True
            return []
        if cum_dd <= -0.10:
            logger.warning("누적 DD -10%% 도달 — 신규진입 차단")
            state.entry_closed = True
            return []

    candidates = []
    cnt = {"total": 0, "no_data": 0, "bar_miss": 0,
           "ctx_miss": 0, "m_long": 0, "s_score": 0, "liq": 0,
           "pullback_vwap": 0}
    failed: Dict[str, List[str]] = {k: [] for k in cnt if k != "total"}

    for ticker in tickers:
        if ticker in state.positions:
            continue
        df_5m = today_dfs.get(ticker)
        if df_5m is None or len(df_5m) < 5:
            cnt["no_data"] += 1; failed["no_data"].append(ticker)
            continue

        # 30분 surge 필터: 직전 폭락봉(3연속 -3%+ body, 5x volume) 감지 시 진입 차단
        if p.get("use_30min_surge_filter", False):
            from strategies.intraday_swing_mom import _has_30min_surge
            if _has_30min_surge(df_5m):
                logger.info(f"  [30분 surge 차단] {ticker} — 폭락 직후 진입 스킵")
                continue

        cnt["total"] += 1

        try:
            # datetime 컬럼이 Datetime 타입일 수 있으므로 명시적 문자열 변환
            _dt_col = df_5m["datetime"]
            _dt_dtype = str(_dt_col.dtype)
            if _dt_col.dtype != pl.Utf8:
                _dt_vals = _dt_col.dt.strftime("%Y-%m-%d %H:%M:%S").to_list()
            else:
                _dt_vals = _dt_col.to_list()
            dt_list = [_ts_str(v) for v in _dt_vals]
            last_bar_hm = dt_list[-1][11:16]
            last_bar_date = dt_list[-1][:10]
            if today_str and last_bar_date != today_str:
                if cnt["bar_miss"] < 3:
                    logger.warning(f"[봉불일치-날짜] {ticker} dtype={_dt_dtype} last_bar_date={last_bar_date} today={today_str} last_ts={dt_list[-1]} first_ts={dt_list[0]} n_bars={len(dt_list)}")
                cnt["bar_miss"] += 1; failed["bar_miss"].append(ticker)
                continue
            cur_h, cur_m = int(current_bar_time[:2]), int(current_bar_time[3:5])
            bar_h, bar_m = int(last_bar_hm[:2]), int(last_bar_hm[3:5])
            cur_total = cur_h * 60 + cur_m
            bar_total = bar_h * 60 + bar_m
            # RF-D15: 미래봉(bar_total > cur_total + 3min) 거부. NTP 드리프트/KIS 클럭 스큐 최대 3분 허용.
            # stale(>15분 지연)도 거부. 동일/근접 bar는 정상.
            if bar_total > cur_total + 3:
                if cnt["bar_miss"] < 3:
                    logger.warning(f"[미래봉-거부] {ticker} dtype={_dt_dtype} last_bar={dt_list[-1]} cur_bar={current_bar_time} future={bar_total-cur_total}min bars={len(dt_list)}")
                cnt["bar_miss"] += 1; failed["bar_miss"].append(ticker)
                continue
            if cur_total - bar_total > 15:
                if cnt["bar_miss"] < 3:
                    logger.warning(f"[봉불일치-stale] {ticker} dtype={_dt_dtype} last_bar={dt_list[-1]} cur_bar={current_bar_time} delay={cur_total-bar_total}min bars={len(dt_list)} first={dt_list[0]}")
                cnt["bar_miss"] += 1; failed["bar_miss"].append(ticker)
                continue

            # 마지막 bar의 context 직접 조회 → 게이트별 탈락 원인 파악
            last_ts = dt_list[-1]
            ctx = get_context_for_5m_bar(last_ts, context_map, ticker)
            if ctx is None:
                cnt["ctx_miss"] += 1; failed["ctx_miss"].append(ticker)
            else:
                # 백테스트와 동일한 게이트 함수 사용 (정합성 보장)
                gate_pass = check_regime_gate_swing(ctx, p)
                if not gate_pass:
                    # 진단 집계 (로그용 — 어떤 필터에서 탈락했는지 기록)
                    if ctx.m_long < p.get("m_long_min", 0.60):
                        cnt["m_long"] += 1; failed["m_long"].append(ticker)
                        if cnt["m_long"] <= 3:
                            stock_label = f"{_get_stock_name(ticker)}({ticker})"
                            logger.info(
                                f"  [M_long] {stock_label} bar={ctx.bar_ts} "
                                f"m_long={ctx.m_long:.2f} (need>={p.get('m_long_min', 0.60):.2f}) "
                                f"s={ctx.s_score:.2f} br={ctx.breadth_ratio:.2f} "
                                f"factors=vwap:{int(ctx.m_vwap_up)} ema:{int(ctx.m_ema_up)} "
                                f"idx:{int(ctx.m_idx_up)} breadth:{int(ctx.m_breadth_ok)} "
                                f"idx_ret={ctx.m_index_ret*100:+.2f}%"
                            )
                    if ctx.s_score < p.get("s_min", 0.60):
                        cnt["s_score"] += 1; failed["s_score"].append(ticker)
                    if ctx.liquidity_rank < p.get("liquidity_rank_min", 0.40):
                        cnt["liq"] += 1; failed["liq"].append(ticker)
                else:
                    # 게이트 통과 → pullback/vwap 필터까지 확인
                    sigs = _generate_signals_for_ticker(df_5m, context_map, ticker, p)
                    sigs = [s for s in sigs if s.signal_idx == len(dt_list) - 1]
                    if not sigs:
                        cnt["pullback_vwap"] += 1; failed["pullback_vwap"].append(ticker)
                        if cnt["pullback_vwap"] <= 5:
                            diag = inspect_signal_bar_swing_mom(
                                df_5m, context_map, ticker, p, signal_idx=len(dt_list) - 1
                            )
                            if diag:
                                stock_label = f"{_get_stock_name(ticker)}({ticker})"
                                e_long = diag.get("e_long")
                                e_long_str = f"{e_long:.3f}" if isinstance(e_long, (int, float)) else "n/a"
                                vwap_gap_pct = diag.get("vwap_gap_pct")
                                vwap_gap_str = (
                                    f"{vwap_gap_pct * 100:+.2f}%"
                                    if isinstance(vwap_gap_pct, (int, float))
                                    else "n/a"
                                )
                                logger.info(
                                    f"  [5m진단] {stock_label} bar={diag['signal_ts']} "
                                    f"pullback={diag['pullback_ok']}/{diag['pullback_len']} "
                                    f"vwap_ok={diag['vwap_ok']} gap={vwap_gap_str} "
                                    f"e={e_long_str} (need>={diag['e_long_min']:.3f})"
                                )
                    else:
                        best = max(sigs, key=lambda s: s.rank_score)
                        candidates.append({
                            "ticker":     ticker,
                            "signal":     best,
                            "signal_idx": best.signal_idx,
                            "rank_score": best.rank_score,
                        })
        except Exception as e:
            logger.debug(f"{ticker} 신호 처리 오류: {e}")

    _LABELS = {
        "no_data": "데이터없음", "bar_miss": "봉불일치", "ctx_miss": "ctx없음",
        "m_long": "M_long", "s_score": "S_score",
        "liq": "유동성", "pullback_vwap": "pullback/vwap",
    }
    logger.info(
        f"[SWING 필터] 전체={cnt['total']} "
        f"데이터없음={cnt['no_data']} 봉불일치={cnt['bar_miss']} "
        f"ctx없음={cnt['ctx_miss']} M_long={cnt['m_long']} "
        f"S_score={cnt['s_score']} "
        f"유동성={cnt['liq']} pullback/vwap={cnt['pullback_vwap']} "
        f"→ 신호={len(candidates)}"
    )
    for key, label in _LABELS.items():
        if failed[key]:
            names = [_get_stock_name(t) for t in failed[key]]
            logger.info(f"  [{label}] {' '.join(names)}")
    if candidates:
        details = [
            f"{_get_stock_name(c['ticker'])}({c['ticker']},e={c['signal'].e_long:.3f},rank={c['rank_score']:.3f})"
            for c in candidates
        ]
        logger.info(f"  [신호 통과] {details}")

    # rank_score 최소 기준 적용 (저품질 신호 제거)
    min_rank = p.get("min_rank_score", 0.0)
    if min_rank > 0:
        before = len(candidates)
        candidates = [c for c in candidates if c["rank_score"] >= min_rank]
        if before > len(candidates):
            logger.info(f"  [rank 필터] {before - len(candidates)}개 제거 (rank < {min_rank:.2f})")

    candidates.sort(key=lambda x: x["rank_score"], reverse=True)
    return candidates[: p.get("top_n", 8)]


# ── 포지션 관리 (Multi-TP) ────────────────────────────────────────────────────

def _manage_positions(
    state: TradingState,
    today_dfs: Dict[str, pl.DataFrame],
    kis_client,
    p: dict,
    notifier=None,
    scheduler=None,
):
    """오픈 포지션 SL/TP1/TP2/TimeStop/EOD 체크 → 자동 매도."""
    closed = []
    now = _now_hhmm()

    for ticker, pos in list(state.positions.items()):
        if pos.status == "CLOSED":
            closed.append(ticker)
            continue

        df = today_dfs.get(ticker)
        if df is None or len(df) == 0:
            continue

        # RF-D5: entry_bar_idx 기반 스킵 제거 (오버나잇 시 오늘 df 가 0부터 시작해
        # 어제 entry_bar_idx 보다 작아지면 SL/TP 전부 스킵되던 버그 수정)
        rows = df.to_dicts()

        latest  = rows[-1]
        cur_bar_idx = len(rows) - 1
        cur_high  = float(latest.get("high",  pos.entry_price))
        cur_low   = float(latest.get("low",   pos.entry_price))
        cur_close = float(latest.get("close", pos.entry_price))

        # RF-D8: 이전 봉에서 SL/TP 터치 후 현재 봉에서 회복 시 미스하는 버그 수정.
        # 오늘 봉 중 진입 이후 전체를 스캔하여 극값 보조 판정.
        _entry_ts_str = str(pos.entry_ts)[:16]  # "YYYY-MM-DD HH:MM"
        for _r in rows:
            if str(_r.get("datetime", ""))[:16] < _entry_ts_str:
                continue
            _r_low  = float(_r.get("low",  pos.entry_price))
            _r_high = float(_r.get("high", pos.entry_price))
            if _r_low < cur_low:
                cur_low = _r_low
            if _r_high > cur_high:
                cur_high = _r_high

        # RF-D8b: 실시간 현재가로 SL 보조 체크 (5분봉 사이 급락 대응)
        _upper_limit: float = 0.0  # 상한가 가격 (0=미조회)
        if kis_client is not None:
            _rt_price, _rt_uplmt = kis_client.get_price_and_limit(ticker)
            if _rt_price and _rt_price > 0:
                if _rt_price < cur_low:
                    cur_low = _rt_price
                if _rt_price > cur_high:
                    cur_high = _rt_price
                cur_close = _rt_price  # 최신 체결가로 갱신
            if _rt_uplmt and _rt_uplmt > 0:
                _upper_limit = _rt_uplmt
        # RF-D6: KRX 정규장(09:00~15:30) 5분봉 누적 카운트로 bars_held 계산.
        # 이전 벽시계 기반 (elapsed_secs/300) 은 장 마감/야간/주말을 포함해
        # 234봉(≈3거래일) 대신 19.5시간 벽시계 후 발화되는 버그가 있었음.
        pos.bars_held = _rth_bars_between(str(pos.entry_ts), datetime.now())

        # 마이너스 구간 경험 추적 (회복TP 판단용)
        # cur_close 기준으로 실제 마이너스 상태일 때만 설정 (저가 기준은 너무 쉽게 트리거됨)
        if cur_close < pos.entry_price:
            pos.was_negative = True

        exit_price  = None
        exit_reason = None
        qty_to_sell = 0

        # ── 분할매수 2차 체크 (SL 판정 전) ──────────────────────────────────
        # 기존 execution_gate S2 방식: 현재가 < 1차 진입가 + SL 안전장치
        _max_addon_count = max(0, int(p.get("max_addon_count", 2)))
        if pos.addon_count >= _max_addon_count:
            pos.addon_done = True
        if not pos.addon_done and pos.addon_qty > 0 and pos.addon_count < _max_addon_count:
            _buf = float(p.get("add_trigger_buf", 0.0015))  # 백테스트와 동일 버퍼 적용
            _trigger_px   = pos.entry_price * (1 - _buf)
            _below_entry  = cur_close < _trigger_px         # 진입가 - 버퍼(기본 0.15%) 이하
            _above_sl     = cur_low   > pos.sl_price        # SL 터치 안함 (안전장치)
            _same_bar_addon = (pos.addon_last_bar_idx == cur_bar_idx)
            if _below_entry and _above_sl and not _same_bar_addon:
                logger.info(
                    f"[분할매수] {ticker} 조건 충족 "
                    f"cur_close={cur_close:.0f} < entry={pos.entry_price:.0f} "
                    f"& cur_low={cur_low:.0f} > sl={pos.sl_price:.0f}  "
                    f"+{pos.addon_qty}주"
                )
                _ar = kis_client.buy_market(ticker, pos.addon_qty)
                if _ar.get("success"):
                    # 가중평균 진입가 재계산 (addon_ratio 기반)
                    _old_qty = pos.qty_remaining
                    _new_qty = pos.addon_qty
                    _addon_fill = kis_client.get_current_price(ticker) or cur_close
                    _avg_entry = (pos.entry_price * _old_qty + _addon_fill * _new_qty) / (_old_qty + _new_qty)
                    logger.info(
                        f"  [분할매수] 체결 @{_addon_fill:.0f}  "
                        f"avg_entry: {pos.entry_price:.0f} -> {_avg_entry:.0f}"
                    )
                    pos.entry_price = _avg_entry
                    pos.sl_price = _avg_entry * (1 - p["sl_pct"])
                    _tp1 = p.get("tp1_pct") or p.get("tp_pct", 0.12)
                    _tp2 = p.get("tp2_pct") or _tp1  # 2-tier TP 유지 (없으면 단일TP 폴백)
                    pos.tp1_price = _avg_entry * (1 + _tp1)
                    pos.tp2_price = _avg_entry * (1 + _tp2)
                    pos.qty_remaining += _new_qty
                    pos.qty_total     += _new_qty
                    pos.addon_count += 1
                    pos.addon_last_bar_idx = cur_bar_idx
                    pos.addon_done = (pos.addon_count >= _max_addon_count)
                    _save_state(state)
                else:
                    _fail_msg = (_ar.get("msg") or "").strip()
                    logger.warning(f"  [분할매수] 주문 실패: {_ar}")
                    # A4 fix: 실패 사유와 관계없이 addon_done=True — 무한 재시도 방지
                    pos.addon_done = True
                    if "주문가능금액" in _fail_msg or "주문가능수량" in _fail_msg:
                        logger.warning(f"  [분할매수] {ticker} 잔액 부족으로 분할매수 비활성화")
                    else:
                        logger.warning(f"  [분할매수] {ticker} 주문 실패 — 분할매수 비활성화 (재시도 없음)")
                    # addon_done=True 재시작 후 유지 위해 모든 실패 경우 저장
                    _save_state(state)

        # Codex US-03 (REVISE round 2): tp1_exit_ratio==0 → Leg1 elif 체인을
        # 완전히 스킵하기 위해 진입 시점에 leg1_done=True 로 전환. Leg1 분기에
        # 들어가면 같은 bar 의 time_stop/eod 평가가 막혀 청산이 지연되는 문제 방지.
        # 신규/복구/동적 config 변경 모두 커버.
        _tp1_ratio_init = float(p.get("tp1_exit_ratio", 0.5))
        if _tp1_ratio_init == 0.0 and not pos.leg1_done:
            pos.leg1_done = True
            pos.leg1_done_bar_idx = max(pos.leg1_done_bar_idx, cur_bar_idx)
            _ensure_leg2_allocation(pos, p)
            logger.debug(
                f"[TP1 skip] {pos.ticker} tp1_exit_ratio=0 → Leg2 즉시 전환 (no order)"
            )
        if pos.leg1_done_bar_idx >= 0 and not pos.leg1_done:
            pos.leg1_done = True
            _ensure_leg2_allocation(pos, p)

        if not pos.leg1_done:
            # --- Leg1 단계 ---
            if cur_low <= pos.sl_price:
                # 시장가 SL: cur_low * (1 - SLIPPAGE_RATE) 보수적 추정
                exit_price  = round(cur_low * (1.0 - SLIPPAGE_RATE), 0)
                exit_reason = "full_stop"
                qty_to_sell = pos.qty_remaining
                logger.debug(
                    f"[SL] {pos.ticker} cur_low={cur_low:.0f} "
                    f"→ fill_est={exit_price:.0f} (slippage {SLIPPAGE_RATE*100:.1f}%)"
                )
            elif pos.was_negative and cur_close >= pos.entry_price * (1 + float(p.get("recovery_tp_pct", 0.01))):
                # 마이너스 후 회복 TP: 한 번이라도 마이너스 경험 → +1% 도달 시 전량 청산
                # 단, 상한가 도달 시 다음 날까지 홀드 (time_stop과 동일 면제 정책)
                _at_limit_up_l1 = _upper_limit > 0 and cur_close >= _upper_limit * 0.999
                if _at_limit_up_l1:
                    logger.info(
                        f"  [recovery_tp 면제] {ticker} 상한가({_upper_limit:.0f}) 도달 "
                        f"→ recovery_tp 건너뜀, 홀드 유지"
                    )
                else:
                    # 전량 청산 대신 tp1 비율(15%)만 청산 → 나머지는 leg2 trail로 더 수익 추구
                    _tp1_ratio = float(p.get("tp1_exit_ratio", 0.15))
                    _rtp_qty   = max(1, round(pos.qty_remaining * _tp1_ratio))
                    exit_price  = cur_close
                    exit_reason = "recovery_tp"
                    qty_to_sell = _rtp_qty
                    # leg1_done은 매도 성공 후 설정 (매도 실패 시 full qty가 Leg2로 잘못 전환되는 것 방지)
                    logger.info(
                        f"  [recovery_tp] {ticker} 마이너스 후 +{float(p.get('recovery_tp_pct',0.01))*100:.1f}% 회복 "
                        f"→ {_rtp_qty}주({_tp1_ratio*100:.0f}%) 부분 청산 후 trail 전환 "
                        f"(entry={pos.entry_price:.0f} cur={cur_close:.0f})"
                    )
            elif cur_high >= pos.tp1_price:
                if pos.leg1_done_bar_idx == cur_bar_idx:
                    continue
                # 단일TP 모드(tp1==tp2): 전량 청산
                # 2-tier TP 모드: 50% 부분청산 후 Leg2 진입
                _is_single_tp = (pos.tp1_price >= pos.tp2_price)
                exit_price  = pos.tp1_price
                if _is_single_tp:
                    exit_reason = "full_tp"
                    qty_to_sell = pos.qty_remaining
                else:
                    exit_reason = "tp1"
                    pos.leg1_done = True  # A2 fix: TP1 결정 즉시 Leg1 완료 — 매도 실패/cooldown 시에도 재발동 방지
                    pos.tp1_executed = True  # 실제 TP1 분할매도 실행 표시
                    # Codex US-03 (REVISE): floor(qty_total * ratio).
                    # int(x) 는 양수에서 math.floor 와 동일.
                    # ratio=0.5+짝수 qty: 기존 qty_total//2 와 동일 (회귀 보존).
                    # ratio=0.5+qty=3: int(1.5)=1 == 3//2 (회귀 보존).
                    # ratio=0.0: 0 → TP1 매도 스킵 (의미 일치).
                    # ratio=1.0: 전량 매도.
                    _tp1_ratio = float(p.get("tp1_exit_ratio", 0.5))
                    qty_to_sell = int(pos.qty_total * _tp1_ratio)
                    qty_to_sell = min(qty_to_sell, pos.qty_remaining)
                    if qty_to_sell <= 0:
                        # ratio=0 또는 산출 결과 0 → TP1 매도 스킵.
                        # exit_reason 초기화하여 아래 매도 블록(`if exit_reason
                        # and qty_to_sell > 0`) 을 건너뛰게 함.
                        exit_reason = None
            elif pos.bars_held >= p.get("time_stop_bars", 120):
                # 상한가 포지션은 time_stop 청산 면제 — 다음 날까지 홀드
                _at_limit_up = _upper_limit > 0 and cur_close >= _upper_limit * 0.999
                if _at_limit_up:
                    logger.info(
                        f"  [time_stop 면제] {ticker} 상한가({_upper_limit:.0f}) 도달 "
                        f"→ bars_held={pos.bars_held} 초과해도 홀드 유지"
                    )
                else:
                    exit_price  = cur_close
                    exit_reason = "time_stop"
                    qty_to_sell = pos.qty_remaining
            elif _is_eod_force(now):
                exit_price  = cur_close
                exit_reason = "eod"
                qty_to_sell = pos.qty_remaining
        else:
            # --- Leg2 단계 (breakeven SL) ---
            _ensure_leg2_allocation(pos, p)
            if cur_high > pos.leg2_peak:
                pos.leg2_peak = cur_high
            trail_pct = float(p.get("tp2_trail_pct", 0.0) or 0.0)
            trail_active = (
                pos.leg2_trail_qty > 0
                and trail_pct > 0
                and pos.leg2_peak > pos.entry_price * 1.005
            )
            trail_stop = pos.leg2_peak * (1.0 - trail_pct) if trail_active else 0.0
            if cur_low <= pos.entry_price:
                # breakeven SL도 시장가 체결 → 슬리피지 적용
                exit_price  = round(cur_low * (1.0 - SLIPPAGE_RATE), 0)
                exit_reason = "breakeven_stop"
                qty_to_sell = pos.qty_remaining
                logger.debug(
                    f"[BE_SL] {pos.ticker} cur_low={cur_low:.0f} "
                    f"→ fill_est={exit_price:.0f} (slippage {SLIPPAGE_RATE*100:.1f}%)"
                )
            elif trail_active and cur_low <= trail_stop:
                exit_price  = round(cur_low * (1.0 - SLIPPAGE_RATE), 0)
                exit_reason = "trail_stop"
                qty_to_sell = pos.leg2_trail_qty
            elif pos.leg2_fixed_qty > 0 and cur_high >= pos.tp2_price:
                exit_price  = pos.tp2_price
                exit_reason = "tp2"
                qty_to_sell = pos.leg2_fixed_qty
            elif pos.bars_held >= p.get("time_stop_bars", 120):
                # 상한가 포지션은 time_stop 청산 면제 — 다음 날까지 홀드
                _at_limit_up = _upper_limit > 0 and cur_close >= _upper_limit * 0.999
                if _at_limit_up:
                    logger.info(
                        f"  [time_stop 면제-L2] {ticker} 상한가({_upper_limit:.0f}) 도달 "
                        f"→ bars_held={pos.bars_held} 초과해도 홀드 유지"
                    )
                else:
                    exit_price  = cur_close
                    exit_reason = "time_stop_l2"
                    qty_to_sell = pos.qty_remaining
            elif _is_eod_force(now):
                exit_price  = cur_close
                exit_reason = "eod_l2"   # Leg2 EOD — runner 와 reason 일관성
                qty_to_sell = pos.qty_remaining

        # 매도 주문 기접수 대기 중 — cooldown 동안 재시도 차단
        # SL 계열은 cooldown 무시 (손절 지연 방지)
        _SL_REASONS = {"full_stop", "breakeven_stop"}
        if (exit_reason and qty_to_sell > 0
                and exit_reason not in _SL_REASONS
                and pos.sell_blocked_until > time.time()):
            logger.info(
                f"  [sell대기] {ticker} 기접수 주문 체결 대기 중 "
                f"({pos.sell_blocked_until - time.time():.0f}초 남음) — 청산 건너뜀"
            )
            exit_reason = None

        if exit_reason and qty_to_sell > 0:
            pnl = (exit_price - pos.entry_price) * qty_to_sell
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
            # 수익률 sanity check: 비정상적인 값만 경고 (실제 100% 이상 수익은 가능)
            if abs(pnl_pct) > 50:
                logger.warning(f"[pnl_pct 이상] {ticker} pnl_pct={pnl_pct:.2f}% — 확인 필요")

            logger.info(
                f"[청산] {ticker} {exit_reason} "
                f"qty={qty_to_sell} 진입={pos.entry_price:.0f} → {exit_price:.0f} "
                f"P&L={pnl_pct:+.2f}%"
            )

            result = _sell_market_with_retry(
                kis_client, ticker, qty_to_sell, context=f"exit={exit_reason}"
            )
            if result["success"]:
                pos.sell_fail_count = 0
                pos.realized_pnl  += pnl
                state.daily_pnl   += pnl
                pos.qty_remaining -= qty_to_sell

                # 연속 SL 스트릭 추적 — 3연속 SL 시 30분 신규 진입 차단
                _SL_EXIT_REASONS = {"full_stop", "breakeven_stop"}
                if exit_reason in _SL_EXIT_REASONS:
                    state.consecutive_sl_count += 1
                    _STREAK_LIMIT = 3
                    _COOLDOWN_SECS = 30 * 60
                    if state.consecutive_sl_count >= _STREAK_LIMIT:
                        state.sl_cooldown_until = time.time() + _COOLDOWN_SECS
                        _sl_msg = (
                            f"⛔ [연속SL] {state.consecutive_sl_count}연속 손절 — "
                            f"30분 신규 진입 차단 (해제 {_COOLDOWN_SECS//60}분 후)"
                        )
                        logger.warning(_sl_msg)
                        if notifier:
                            notifier.send_message(_sl_msg)
                elif pnl > 0:
                    # 수익 청산 시 스트릭 리셋
                    state.consecutive_sl_count = 0

                # Daily Stop 체크
                if (DAILY_STOP_LOSS_PCT > 0 and state.initial_equity > 0
                        and not state.entry_closed
                        and state.daily_pnl / state.initial_equity < -DAILY_STOP_LOSS_PCT):
                    state.entry_closed = True
                    msg = (f"🛑 [SWING-MOM] Daily Stop 발동 — "
                           f"일간손실 {state.daily_pnl:+,.0f}원 "
                           f"({state.daily_pnl/state.initial_equity*100:.2f}%) "
                           f"기준 -{DAILY_STOP_LOSS_PCT*100:.1f}% 초과. 신규 진입 중단.")
                    logger.warning(msg)
                    if notifier:
                        notifier.send_message(msg)

                if exit_reason in ("tp1", "recovery_tp"):
                    pos.leg1_done = True
                    pos.leg1_done_bar_idx = cur_bar_idx
                    pos.status    = "LEG1_DONE"
                    _ensure_leg2_allocation(pos, p)
                    logger.info(
                        f"  Leg1 WIN: {ticker} 잔여={pos.qty_remaining}주 "
                        f"SL→breakeven({pos.entry_price:.0f})"
                    )
                    if pos.qty_remaining <= 0:
                        pos.status = "CLOSED"
                        closed.append(ticker)
                else:
                    if exit_reason == "trail_stop":
                        pos.leg2_trail_qty = max(0, pos.leg2_trail_qty - qty_to_sell)
                    elif exit_reason == "tp2":
                        pos.leg2_fixed_qty = max(0, pos.leg2_fixed_qty - qty_to_sell)
                    else:
                        pos.leg2_fixed_qty = 0
                        pos.leg2_trail_qty = 0

                    if pos.qty_remaining <= 0:
                        pos.status = "CLOSED"
                        closed.append(ticker)
                    else:
                        pos.status = "LEG1_DONE" if pos.leg1_done else "OPEN"

                if scheduler:
                    scheduler.record_trade(
                        ticker=ticker,
                        name=_get_stock_name(ticker),
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        qty=qty_to_sell,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                    )
                # state.history 에 청산 기록 추가 (전략 탭 총 거래 카운트)
                state.history.append({
                    "ticker":      ticker,
                    "name":        _get_stock_name(ticker),
                    "entry_price": pos.entry_price,
                    "exit_price":  exit_price,
                    "qty":         qty_to_sell,
                    "pnl_pct":     round(pnl_pct, 2),
                    "reason":      exit_reason,
                    "exit_time":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                # 대시보드 trading.db 기록 (저널/인사이트/통계 탭)
                try:
                    _journal.record_trade({
                        "code":          ticker,
                        "name":          _get_stock_name(ticker),
                        "trade_type":    "sell",
                        "decision":      "sell",
                        "price":         exit_price,
                        "qty":           qty_to_sell,
                        "buy_price":     pos.entry_price,
                        "return_rate":   round(pnl_pct, 4),
                        "trigger_type":  "swing_mom",
                        "source":        "swing_mom_kr",
                        "sell_rationale": exit_reason,
                        "regime":        "",
                    }, exit_type=exit_reason)
                except Exception as _je:
                    logger.warning(f"[Journal] 청산 기록 실패: {_je}")
                # Codex US-04: dual-write — canonical trade_events 테이블에도 동시 기록.
                try:
                    _journal.record_trade_event(TradeEvent(
                        event_ts=TradeEvent.now_ts(),
                        ticker=ticker,
                        side="SELL",
                        entry_price=float(pos.entry_price),
                        exit_price=float(exit_price),
                        qty=int(qty_to_sell),
                        pnl=float(pnl),
                        pnl_pct=round(float(pnl_pct), 4),
                        reason=exit_reason or "",
                        source="swing_mom_kr",
                    ))
                except Exception as _te:
                    logger.warning(f"[TradeEvent] 청산 기록 실패: {_te}")
                if notifier:
                    # 분할매도 후 최종 청산: 합산 PnL 표시
                    _total_pnl = None
                    _total_pnl_pct = None
                    _is_final_partial = (
                        pos.qty_remaining <= 0
                        and pos.leg1_done
                        and exit_reason not in ("tp1", "recovery_tp")
                    )
                    if _is_final_partial:
                        _total_pnl = pos.realized_pnl
                        _total_pnl_pct = (
                            pos.realized_pnl
                            / (pos.entry_price * pos.qty_total)
                            * 100
                        )
                    notifier.send_trade_exit(
                        strategy="SWING-MOM",
                        ticker=f"{_get_stock_name(ticker)}({ticker})",
                        exit_reason=exit_reason,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        qty=qty_to_sell,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        bars_held=pos.bars_held,
                        mode_str="[모의]" if IS_MOCK else "[실전]",
                        partial=(exit_reason in ("tp1", "recovery_tp")),
                        total_pnl=_total_pnl,
                        total_pnl_pct=_total_pnl_pct,
                    )
            else:
                logger.error(f"  매도 실패: {result['msg']}")
                # 수량 초과 오류 = 이미 매도 주문 접수됐거나 수동 청산된 상황
                if result.get("pending_order"):
                    # 브로커 실제 잔고로 확인
                    _actual_qty = 0
                    try:
                        _bal = kis_client.get_balance() if kis_client else []
                        _bal_map = {b.get("pdno", ""): int(b.get("hldg_qty", 0) or 0) for b in _bal}
                        _actual_qty = _bal_map.get(ticker, 0)
                    except Exception:
                        pass
                    if _actual_qty == 0:
                        # 브로커에 없음 = 수동 청산 or 이미 체결 완료 → 즉시 CLOSED
                        pos.status = "CLOSED"
                        pos.qty_remaining = 0
                        closed.append(ticker)
                        logger.warning(
                            f"  [수동청산감지] {ticker} 브로커 잔고=0 "
                            f"→ 포지션 CLOSED 처리 (Telegram 없음)"
                        )
                    else:
                        # 일부 잔고 남음 → qty 보정 후 대기
                        pos.qty_remaining = _actual_qty
                        pos.sell_fail_count += 1
                        if pos.sell_fail_count >= 3:
                            # 3회 연속 pending_order+잔고불일치 → 무한루프 방지 강제 CLOSED
                            pos.status = "CLOSED"
                            pos.qty_remaining = 0
                            closed.append(ticker)
                            logger.error(
                                f"  [매도루프차단] {ticker} pending_order 연속 {pos.sell_fail_count}회 "
                                f"— 강제 CLOSED (수동 확인 필요)"
                            )
                            if notifier:
                                try:
                                    notifier.send_message(
                                        f"🚨 [SWING-MOM] {ticker} 매도 루프 강제 종료 "
                                        f"— 브로커 잔고={_actual_qty}주 수동 확인 필요"
                                    )
                                except Exception:
                                    pass
                        else:
                            pos.sell_blocked_until = time.time() + 120  # A3 fix: 1시간→2분 (SL은 이미 우회하므로 짧게)
                            logger.warning(
                                f"  [포지션보정] {ticker} 실제잔고={_actual_qty}주 "
                                f"→ qty_remaining 갱신, 2분 차단 (실패 {pos.sell_fail_count}/3)"
                            )
                else:
                    # 진짜 매도 실패 — 쿨다운 (Telegram 성공 여부 무관)
                    _tg_cooldown_ok = pos.sell_blocked_until < time.time()
                    if _tg_cooldown_ok:
                        pos.sell_blocked_until = time.time() + 120  # A3 fix: 1시간→2분 (SL은 이미 우회)
                        logger.warning(
                            f"  [매도차단] {ticker} 매도 최종 실패 → 2분 재시도 차단"
                        )
                        if notifier:
                            try:
                                notifier.send_message(
                                    f"🚨 [SWING-MOM] 매도 최종 실패 — {ticker} "
                                    f"qty={qty_to_sell} reason={exit_reason} "
                                    f"msg={result.get('msg','')}. 수동 개입 필요."
                                )
                            except Exception:
                                pass
                    else:
                        logger.warning(
                            f"  [알림쿨다운] {ticker} 매도실패 Telegram 중복 차단 "
                            f"({pos.sell_blocked_until - time.time():.0f}초 남음)"
                        )

    for t in closed:
        if t in state.positions and state.positions[t].status == "CLOSED":
            del state.positions[t]

    # 혹시 남아있는 CLOSED 포지션 제거 (좀비 방지)
    state.positions = {k: v for k, v in state.positions.items() if v.status != "CLOSED"}

    # RF-D7: 관리 후 상태 즉시 영속화 (재시작 시 복원용)
    _save_state(state)


# ── 메인 루프 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWING-MOM 실시간 자동매매")
    parser.add_argument("--risk_pct",      type=float, default=0.01,
                        help="종목당 계좌 리스크 비율 (기본 1%%)")
    parser.add_argument("--max_positions", type=int,   default=6,
                        help="최대 동시 보유 종목 수 (기본 6 = top_n)")
    parser.add_argument("--universe_n",    type=int,   default=30,
                        help="거래대금 상위 N종목 유니버스 (백테스트 UNIVERSE_TOP_N=30 매칭)")
    parser.add_argument("--data_dir",      default=DATA_DIR)
    parser.add_argument("--daily_dir",     default=DAILY_DIR)
    args = parser.parse_args()

    # PID lockfile — 중복 실행 방지 (원자적 exclusive create)
    _lock_dir = os.path.join(_ROOT, "locks")
    os.makedirs(_lock_dir, exist_ok=True)
    _lock_path = os.path.join(_lock_dir, "swing_mom.lock")
    import subprocess

    def _is_pid_alive(pid: int) -> bool:
        try:
            _r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, timeout=5,
            )
            return str(pid).encode() in _r.stdout
        except Exception:
            return True  # tasklist 실패 → 살아있다고 보수적 가정

    # 1단계: 기존 lock 파일이 살아있는 프로세스 소유인지 확인
    if os.path.exists(_lock_path):
        try:
            old_pid = int(open(_lock_path).read().strip())
            if _is_pid_alive(old_pid):
                print(f"[LOCK] 이미 실행 중 (PID {old_pid}). 종료합니다.")
                return
            logger.warning(f"[LOCK] 이전 프로세스(PID {old_pid}) 종료됨 — lock 재취득")
            os.remove(_lock_path)
        except Exception as _le:
            logger.warning(f"[LOCK] lock 파일 읽기 실패({_le}) — 기존 lock 삭제 후 진행")
            try:
                os.remove(_lock_path)
            except Exception:
                pass

    # 2단계: 원자적 exclusive create (O_CREAT | O_EXCL) — race condition 차단
    try:
        _fd = os.open(_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(_fd, "w") as _lf:
            _lf.write(str(os.getpid()))
    except FileExistsError:
        # 1단계와 2단계 사이에 다른 프로세스가 먼저 lock 취득
        print("[LOCK] 동시 기동 감지 — 이 인스턴스를 종료합니다.")
        return

    # ── 서버 생존 감시 스레드 ──────────────────────────────────────
    # server.py 가 살아있는 동안에만 봇을 실행한다.
    # server.py 가 종료되면 봇도 정상 종료한다 (독립 실행 시에는 비활성).
    import threading as _threading
    _SERVER_PID_PATH = os.path.join(_ROOT, "state", "server.pid")
    _stop_event = _threading.Event()

    def _server_watchdog():
        import time as _time
        _INTERVAL = 30  # 초
        _grace = 2       # 서버 PID 파일이 처음부터 없으면 독립 실행 모드
        _time.sleep(_grace)
        if not os.path.exists(_SERVER_PID_PATH):
            logger.debug("[Watchdog] server.pid 없음 — 독립 실행 모드")
            return
        logger.info("[Watchdog] 서버 생존 감시 시작")
        while not _stop_event.is_set():
            _stop_event.wait(_INTERVAL)
            if _stop_event.is_set():
                break
            if not os.path.exists(_SERVER_PID_PATH):
                logger.warning("[Watchdog] server.pid 삭제됨 — 서버 종료 감지, 봇 종료")
                _stop_event.set()
                os._exit(0)
            try:
                _srv_pid = int(open(_SERVER_PID_PATH).read().strip())
                if not _is_pid_alive(_srv_pid):
                    logger.warning(f"[Watchdog] 서버(PID={_srv_pid}) 종료 감지 — 봇 종료")
                    _stop_event.set()
                    os._exit(0)
            except Exception:
                pass  # 읽기 실패는 일시적으로 무시

    _wdog = _threading.Thread(target=_server_watchdog, daemon=True, name="server-watchdog")
    _wdog.start()
    # ─────────────────────────────────────────────────────────────

    mode_str = "[모의]" if IS_MOCK else "[실전]"
    logger.info(f"=== SWING-MOM 자동매매 시작 {mode_str} ===")
    logger.info(
        f"리스크={args.risk_pct*100:.1f}%/종목  "
        f"최대포지션={args.max_positions}  "
        f"유니버스={args.universe_n}종목"
    )

    today_str = date.today().isoformat()
    kis = get_client()
    notifier = get_notifier()

    # KIS 토큰 확보: 시작 시 일시적인 네트워크/토큰 회전 윈도우(09:00 KST 부근) 충돌을
    # 1회 실패로 종일 죽지 않게 3회 백오프 재시도.
    _token_attempts = 3
    _token_backoff = 10.0
    for _attempt in range(1, _token_attempts + 1):
        try:
            kis.get_access_token()
            logger.info(f"KIS API 연결 성공 (시도 {_attempt}/{_token_attempts})")
            break
        except Exception as e:
            logger.warning(f"KIS API 연결 실패 시도 {_attempt}/{_token_attempts}: {e}")
            if _attempt == _token_attempts:
                logger.error("KIS API 연결 최종 실패 — 종료")
                return
            time.sleep(_token_backoff)

    all_tickers = _collect_tickers(args.data_dir)
    tickers = _top_n_by_volume(all_tickers, args.daily_dir, n=args.universe_n)
    logger.info(f"초기 유니버스(T-1): {len(tickers)}종목")
    # 빈 유니버스 복구 전략:
    #   1) 첫 실행 등으로 오프라인 캐시가 없는 경우: KIS 거래대금 순위 실시간 조회로 bootstrap.
    #   2) bootstrap 도 실패하면 명시 abort (봇이 0종목을 무한 스캔하지 않도록).
    if not tickers:
        logger.warning(
            "오프라인 유니버스 비어 있음 — KIS 거래대금 순위로 bootstrap 시도"
        )
        try:
            _boot, _ = _fetch_volume_rank(kis, n=args.universe_n)
            if _boot:
                tickers = list(_boot)
                logger.info(f"bootstrap 성공: KIS vol-rank {len(tickers)}종목")
        except Exception as _boot_e:
            logger.warning(f"bootstrap 실패: {_boot_e}")
        if not tickers:
            logger.error(
                "초기 유니버스 확보 불가. data/minute/*_5m.csv + data/daily/*_1d.csv "
                "충전하거나 KIS 거래대금 API 응답을 확인하세요. (종료)"
            )
            return
    liq_scores = _liq_scores(tickers, args.daily_dir)
    sector_map = _load_sector_map(args.data_dir)

    state = TradingState()

    # RF-D7: 이전 세션의 포지션 복원 + 브로커 잔고 reconcile
    # 중요: state 파일 존재 여부와 복원 개수에 무관하게 startup reconcile 은 항상 실행.
    # (파일이 없거나 empty 여도 브로커에 미추적 잔고가 있을 수 있음 — unknown-only 케이스)
    _saved = _load_state()
    _restored = 0
    if _saved:
        _restored = _restore_positions(state, _saved)
        if _restored > 0:
            logger.info(
                f"이전 세션 포지션 복원: {_restored}개 "
                f"(저장일자={_saved.get('saved_date')} 저장시각={_saved.get('saved_at')})"
            )
    _recon = _reconcile_with_broker(state, kis)
    if _recon["aligned"]:
        logger.info(f"  reconcile 일치: {_recon['aligned']}")
    if _recon["mismatch"]:
        logger.warning(f"  reconcile 수량불일치(브로커 기준 보정): {_recon['mismatch']}")
    if _recon["orphaned"]:
        logger.warning(f"  reconcile 브로커에 없음(외부 청산): {_recon['orphaned']}")
    if _recon["unknown"]:
        logger.warning(
            f"  reconcile 브로커에만 존재(미추적): {_recon['unknown']} — "
            f"수동 확인 필요, 자동 복원 안 함"
        )
        # unknown 존재 시 — 자동 재시작 후 복구나 수동 매수로 브로커에만 있는 포지션이
        # 관리 밖에 있다. 신규 진입을 보수적으로 차단해 중복/과다 포지션 리스크를 제거하고,
        # 운영자에게 긴급 알림을 보낸다.
        #
        # 중요: account_value_unknown 은 잔고 재조회 성공 시 해제되므로 별개 플래그
        # entry_blocked_unknown_position 를 사용. 이 플래그는 자동 해제되지 않으며 수동
        # reconcile 후 재시작해야 초기화됨.
        # 차단 비활성화 — 경고만 로깅하고 자동매매 계속 진행
        logger.warning(
            "⚠ 브로커에 미추적 잔고 있음 — 경고만 발생, 신규 진입은 허용."
        )
    try:
        if notifier and (_recon["mismatch"] or _recon["orphaned"] or _recon["unknown"]):
            _alert = (
                f"⚠ [SWING-MOM] 재시작 reconcile 경고 — "
                f"mismatch={len(_recon['mismatch'])} "
                f"orphaned={len(_recon['orphaned'])} "
                f"unknown={len(_recon['unknown'])}"
            )
            if _recon["unknown"]:
                _alert += (
                    f"\n ⚠ unknown 포지션 감지: {_recon['unknown']}\n"
                    f" → 수동 확인 권장 (자동매매는 계속 진행)."
                )
            notifier.send_message(_alert)
    except Exception:
        pass
    if _restored > 0 or _recon["mismatch"] or _recon["orphaned"]:
        _save_state(state)  # 보정 결과 저장

    # ── 인덱스(069500) 과거 데이터 검증 + 백필 ──
    # M_long 계산의 핵심 입력. 히스토리 없으면 재시작마다 M_long=0.00 발생.
    p = LIVE_PARAMS
    _backfill_index_hist(kis, args.data_dir, "069500", days=10)

    for _retry in range(3):
        state.initial_equity = kis.get_account_value()
        if state.initial_equity > 0:
            break
        logger.warning(f"계좌가치 조회 0 — {_retry + 1}/3회 시도, 3초 후 재시도...")
        time.sleep(3)
    if state.initial_equity <= 0:
        fallback_eq = p.get("default_equity", 1_000_000) if IS_MOCK else 0.0
        state.initial_equity = fallback_eq
        if IS_MOCK:
            logger.warning(
                f"⚠ 초기 계좌가치 조회 실패 (3회) — fallback {fallback_eq:,.0f}원으로 진행. "
                f"장 중 첫 성공 조회 시 자동 갱신됩니다."
            )
        state._equity_is_fallback = True
        state.account_value_unknown = not IS_MOCK
        if not IS_MOCK:
            state._equity_is_fallback = False
            msg = (
                "[SEV1] SWING-MOM account value unavailable in production; "
                "blocking new entries until the balance API recovers. "
                "Existing positions remain under exit management."
            )
            logger.error(msg)
            try:
                if notifier:
                    notifier.send_message(msg)
            except Exception as _ne:
                logger.debug(f"SEV1 account-value notify failed: {_ne}")
    else:
        state._equity_is_fallback = False
        state.account_value_unknown = False
        logger.info(f"초기 계좌 잔고: {state.initial_equity:,.0f}원  Daily Stop: {DAILY_STOP_LOSS_PCT*100:.1f}%")
    # [RISK: cumDD] peak_equity 초기화 — initial_equity 기준으로 설정
    state.peak_equity = state.initial_equity

    # Codex US-03: TP 비율 config 검증 — strategies.intraday_swing_mom.validate_tp_config SSOT.
    # tp1_exit_ratio + tp2_trail_ratio <= 1.0 위반 시 ValueError raise (잘못된 config 차단).
    validate_tp_config(p)
    _tp1_r = float(p.get("tp1_exit_ratio", 0.5))
    _tp2_tr = float(p.get("tp2_trail_ratio", 0.0))
    logger.info(f"TP config: tp1_exit_ratio={_tp1_r:.2f} tp2_trail_ratio={_tp2_tr:.2f}")

    scheduler = ReportScheduler("SWING-MOM", notifier, state, "[모의]" if IS_MOCK else "[실전]")
    scheduler.start()
    logger.info("리포트 스케줄러 시작 (08:50/매시정각/12:00/15:40)")

    logger.info(
        f"대기 중... ({p['entry_start']} 진입 시작 — 장 중 실시간 거래대금 순위로 유니버스 갱신)"
    )

    last_bar  = ""
    last_ctx_bar = ""
    context_map: dict = _load_context_cache(today_str)
    # today_dfs 는 while 루프 내부에서 5분봉 완성 시점에 채워지지만, 봇이 15:30 이후
    # 시작되거나 주말/야간 실행처럼 첫 이터레이션에서 바로 종료 브랜치로 진입하면
    # 초기화되지 않아 UnboundLocalError. 빈 dict 로 선초기화.
    today_dfs: Dict[str, pl.DataFrame] = {}

    while True:
        now = _now_hhmm()

        # 장 시작 전 대기 — 하드코드 대신 LIVE_PARAMS["entry_start"] 를 SSOT 로 사용.
        if now < p["entry_start"]:
            logger.info(
                f"[대기] {now} — 유니버스 {len(tickers)}종목 준비 완료, "
                f"{p['entry_start']} 진입 대기 중"
            )
            time.sleep(30)
            continue

        # entry_end 이후 신규 진입 금지
        if now >= p["entry_end"] and not state.entry_closed:
            state.entry_closed = True
            logger.info(f"{p['entry_end']} 진입 마감 — 기존 포지션만 관리")

        # 15:30 이후 종료
        if now >= "15:30" and not state.positions:
            logger.info(f"장 마감. 일간 P&L: {state.daily_pnl:+,.0f}원")
            _save_today_5m(today_dfs, args.data_dir, today_str)
            break
        if now >= "15:45":
            # 장 마감 — candidates 초기화
            state.candidates = []
            _save_candidates([])
            if state.positions:
                overnight_tickers = [
                    f"{tk}({pos.qty_remaining}주)"
                    for tk, pos in state.positions.items()
                    if pos.qty_remaining > 0
                ]
                msg = f"📌 장 종료 — 오버나잇 보유: {', '.join(overnight_tickers)}"
                logger.info(msg)
                if notifier:
                    notifier.send_message(msg)
                _save_state(state)  # RF-D7: 오버나잇 포지션 영속화
            logger.info(f"15:45 종료. 일간 P&L: {state.daily_pnl:+,.0f}원")
            _save_today_5m(today_dfs, args.data_dir, today_str)
            break

        # 5분봉 완성 시점 감지
        now_dt  = datetime.now()
        min_mod = now_dt.minute % 5
        if min_mod != 0 or now_dt.strftime("%H:%M") == last_bar:
            # bar 사이: 보유 종목만 빠르게 체크
            if state.positions:
                pos_tickers = list(state.positions.keys())
                today_dfs = _load_today_5m(
                    pos_tickers, args.data_dir, today_str,
                    kis_client=kis, current_hhmm=now_dt.strftime("%H:%M"),
                )
                _manage_positions(state, today_dfs, kis, p, notifier, scheduler)
            time.sleep(10)
            continue

        # 5분봉 완성 직후 처리
        current_bar = now_dt.strftime("%H:%M")
        last_bar = current_bar
        logger.info(f"--- {current_bar} bar 처리 ---")

        # 실시간 거래대금 순위로 유니버스 갱신 (실패 시 기존 tickers 유지)
        new_tickers, new_scores = _fetch_volume_rank(kis, n=args.universe_n)
        if new_tickers:
            tickers    = new_tickers
            liq_scores = new_scores

        # 전체 유니버스 5분봉 로드
        today_dfs = _load_today_5m(
            tickers, args.data_dir, today_str,
            kis_client=kis, current_hhmm=current_bar,
        )
        logger.info(f"5분봉 로드 완료: {len(today_dfs)}종목 (유니버스 {len(tickers)}종목 중)")
        # 리샘플링 결과 샘플 로그
        for _dbg_t, _dbg_df in list(today_dfs.items())[:2]:
            _dbg_dts = _dbg_df["datetime"].cast(pl.Utf8).to_list()
            logger.info(f"  [{_dbg_t}] {len(_dbg_dts)}봉, 처음={_dbg_dts[0] if _dbg_dts else '?'}, 마지막={_dbg_dts[-1] if _dbg_dts else '?'}")
        if not today_dfs:
            logger.warning("5분봉 데이터 없음")
            time.sleep(30)
            continue

        # 인덱스(069500) 가 유니버스에 없으면 별도 fetch해서 주입 (3회 재시도)
        if "069500" not in today_dfs and kis is not None:
            idx_bars = []
            for _idx_attempt in range(3):
                idx_bars = _fetch_kis_5m(kis, "069500")
                if idx_bars:
                    break
                if _idx_attempt < 2:
                    logger.info(f"인덱스(069500) fetch 재시도 {_idx_attempt+1}/3 (2초 대기)...")
                    time.sleep(2)
            if idx_bars:
                today_dfs["069500"] = _filter_today_until_bar(
                    _resample_to_5m(pl.DataFrame(idx_bars)), today_str, current_bar
                )
                logger.info(f"인덱스(069500) 별도 로드: {len(idx_bars)}봉")
            else:
                logger.warning("인덱스(069500) 3회 fetch 실패 — 히스토리 데이터로 context 빌드 시도")

        # [RISK: crash] KOSPI(069500) 당일 낙폭 -3% 이하 시 강제청산
        _kospi_df = today_dfs.get("069500")
        if _kospi_df is not None and len(_kospi_df) >= 2:
            _kospi_rows = _kospi_df.to_dicts()
            _kospi_open = float(_kospi_rows[0].get("open", 0) or _kospi_rows[0].get("close", 0))
            _kospi_last = float(_kospi_rows[-1].get("close", 0))
            if _kospi_open > 0 and _kospi_last > 0:
                _kospi_ret = (_kospi_last - _kospi_open) / _kospi_open
                if _kospi_ret <= -0.03:
                    logger.warning(
                        f"[RISK: crash] KOSPI 당일 낙폭 {_kospi_ret*100:.2f}%% — "
                        f"강제청산 및 신규진입 차단"
                    )
                    state.entry_closed = True
                    # 모든 포지션 강제청산
                    for _ck_ticker, _ck_pos in list(state.positions.items()):
                        if _ck_pos.status != "CLOSED" and _ck_pos.qty_remaining > 0:
                            _ck_df = today_dfs.get(_ck_ticker)
                            _ck_price = (
                                float(_ck_df.to_dicts()[-1].get("close", _ck_pos.entry_price))
                                if _ck_df is not None and len(_ck_df) > 0
                                else _ck_pos.entry_price
                            )
                            _ck_result = _sell_market_with_retry(
                                kis, _ck_ticker, _ck_pos.qty_remaining, context="crash"
                            )
                            if _ck_result["success"]:
                                _ck_pnl = (_ck_price - _ck_pos.entry_price) * _ck_pos.qty_remaining
                                state.daily_pnl += _ck_pnl
                                _ck_pos.realized_pnl += _ck_pnl
                                _ck_pos.qty_remaining = 0
                                _ck_pos.status = "CLOSED"
                                logger.info(
                                    f"[crash청산] {_ck_ticker} qty={_ck_pos.qty_total} "
                                    f"pnl={_ck_pnl:+,.0f}원"
                                )
                            else:
                                logger.error(
                                    f"[crash청산실패] {_ck_ticker}: {_ck_result.get('msg','')}"
                                )
                    _save_state(state)

        # context_map 재빌드: 장 초반(~10:00)은 매 bar, 이후 30분 주기
        _ctx_has_today = any(k[1].startswith(today_str) for k in context_map) if context_map else False
        _early_session = now_dt.hour < 10  # 09:xx 구간: 데이터 축적 중이므로 매 bar 재빌드
        _need_ctx_rebuild = (
            _early_session              # 장 초반: 매 bar 재빌드 (M_long stale 방지)
            or now_dt.minute % 30 == 0  # 이후: 기존 30분 주기
            or not context_map          # 비어있음
            or not _ctx_has_today       # 오늘 항목 없음
        )
        if current_bar != last_ctx_bar and _need_ctx_rebuild:
            if not _ctx_has_today and context_map:
                logger.info("context_map에 오늘 항목 없음 — 긴급 재빌드")
            logger.info("context_map 재빌드 중...")
            _prev_ctx = context_map  # 캐시 보호: 재빌드 실패 시 복원용
            try:
                _new_ctx = _build_context_map(
                    tickers, today_dfs, args.data_dir,
                    liq_scores, sector_map, today_str,
                )
                # 재빌드 결과가 기존 캐시보다 나쁘면 (오늘 항목 0개) 캐시 유지
                _new_today = sum(1 for k in _new_ctx if k[1].startswith(today_str)) if _new_ctx else 0
                _prev_today = sum(1 for k in _prev_ctx if k[1].startswith(today_str)) if _prev_ctx else 0
                if _new_ctx and _new_today >= _prev_today:
                    context_map = _new_ctx
                elif _new_ctx and _new_today > 0:
                    context_map = _new_ctx
                elif _prev_ctx and _prev_today > 0:
                    logger.warning(
                        f"재빌드 결과 열화 (신규 오늘={_new_today} < 캐시 오늘={_prev_today}) "
                        f"— 캐시 유지"
                    )
                else:
                    context_map = _new_ctx or _prev_ctx or {}
            except Exception as _ctx_e:
                logger.exception(f"context_map 빌드 예외 (기존 map 유지): {_ctx_e}")
                context_map = _prev_ctx or {}
            last_ctx_bar = current_bar
            logger.info(f"context_map: {len(context_map)}개 항목")
            if context_map:
                # 오늘 데이터 중 m_long 분포 진단
                today_ctx = {k: v for k, v in context_map.items() if k[1].startswith(today_str)}
                if today_ctx:
                    m_vals = [v.m_long for v in today_ctx.values()]
                    m_max = max(m_vals)
                    m_pass = sum(1 for m in m_vals if m >= p.get("m_long_min", 0.60))
                    sample = list(today_ctx.items())[-2:]  # 가장 최근 bar 샘플
                    logger.info(
                        f"[오늘 context] {len(today_ctx)}항목, "
                        f"m_long 최대={m_max:.2f}, 통과(>={p.get('m_long_min',0.60):.2f})={m_pass}개"
                    )
                    logger.info(f"  최근 샘플: {[(k, f'm={v.m_long:.2f},s={v.s_score:.2f},d={v.d_score:.2f},br={v.breadth_ratio:.2f}') for k,v in sample]}")
                    if m_pass == 0:
                        logger.warning(
                            f"⚠ 오늘 m_long 최대값={m_max:.2f} < 필요값={p.get('m_long_min',0.60):.2f} "
                            f"→ 시장 약세로 모든 종목 M_long 필터 탈락 예상"
                        )
                else:
                    # 오늘 데이터 없으면 히스토리에서 샘플
                    sample = list(context_map.items())[-2:]
                    logger.info(f"context_map 샘플 (히스토리): {[(k, f'm={v.m_long:.2f},s={v.s_score:.2f},d={v.d_score:.2f}') for k,v in sample]}")
                    logger.warning("오늘 날짜의 context 항목 없음 — 인덱스 또는 종목 5분봉 데이터 부족 가능")
            if not context_map:
                logger.warning("context_map 비어있음 — 이번 bar 신호 탐지 불가")

        # fallback equity → 장 중 첫 성공 조회 시 자동 갱신
        if getattr(state, '_equity_is_fallback', False) or getattr(state, 'account_value_unknown', False):
            _real_eq = kis.get_account_value()
            if _real_eq > 0:
                logger.info(f"계좌가치 갱신: fallback {state.initial_equity:,.0f}원 → 실제 {_real_eq:,.0f}원")
                state.initial_equity = _real_eq
                state._equity_is_fallback = False
                state.account_value_unknown = False
                # [RISK: cumDD] fallback → 실제 전환 시 peak_equity 도 갱신
                if state.peak_equity <= 0:
                    state.peak_equity = _real_eq

        # 포지션 관리
        _manage_positions(state, today_dfs, kis, p, notifier, scheduler)

        # [RISK: cumDD] peak_equity 갱신 — 실현 손익 기준 현재 자산가치
        if state.peak_equity > 0 and not state._equity_is_fallback:
            _cur_equity = state.initial_equity + state.daily_pnl
            if _cur_equity > state.peak_equity:
                state.peak_equity = _cur_equity

        # RF-007: 미실현 손익 포함 Daily Stop 재검사 (신호 스캔 전)
        # fallback equity 사용 중이면 Daily Stop 정확도 떨어짐 — 스킵
        if DAILY_STOP_LOSS_PCT > 0 and state.initial_equity > 0 and not state.entry_closed and not state._equity_is_fallback:
            unrealized = sum(
                ((kis.get_current_price(pos.ticker) or pos.entry_price) - pos.entry_price) * pos.qty_remaining
                for pos in state.positions.values()
                if pos.status != "CLOSED"
            )
            total_pnl = state.daily_pnl + unrealized
            if total_pnl / state.initial_equity < -DAILY_STOP_LOSS_PCT:
                state.entry_closed = True
                msg = (f"🛑 [SWING-MOM] Daily Stop(미실현포함) 발동 — "
                       f"실현 {state.daily_pnl:+,.0f}원 + 미실현 {unrealized:+,.0f}원 = "
                       f"합계 {total_pnl:+,.0f}원 "
                       f"({total_pnl/state.initial_equity*100:.2f}%) "
                       f"기준 -{DAILY_STOP_LOSS_PCT*100:.1f}% 초과. 신규 진입 중단.")
                logger.warning(msg)
                if notifier:
                    notifier.send_message(msg)

        # 신호 탐지
        if state.entry_closed:
            logger.debug("신호 스캔 스킵: entry_closed=True")
        elif len(state.positions) >= args.max_positions:
            logger.debug(f"신호 스캔 스킵: max_positions 도달 ({len(state.positions)}/{args.max_positions})")
        if not IS_MOCK and getattr(state, 'account_value_unknown', False):
            logger.warning("New SWING-MOM entries blocked: account value is unknown in production.")
        if (
            not state.entry_closed
            and len(state.positions) < args.max_positions
            and not (not IS_MOCK and getattr(state, 'account_value_unknown', False))
        ):
            logger.info(f"신호 스캔 시작: {len(tickers)}종목 대상 (context {len(context_map)}개)")
            signals = _check_signals(
                tickers, today_dfs, context_map, state, current_bar, p,
                today_str=today_str,
            )
            # Codex US-02: prevent_same_day_reentry — 옵션 활성화 시 오늘 이미
            # 진입한 종목 신호를 후속 윈도우에서 차단. 날짜 바뀌면 자동 reset.
            today_iso = date.today().isoformat()
            if state.daily_entered_date != today_iso:
                state.daily_entered = set()
                state.daily_entered_date = today_iso
            if p.get("prevent_same_day_reentry", False) and signals:
                _before = len(signals)
                signals = [s for s in signals if s["ticker"] not in state.daily_entered]
                _filtered = _before - len(signals)
                if _filtered > 0:
                    logger.info(
                        f"  [dedup] prevent_same_day_reentry=True — "
                        f"{_filtered}개 신호 차단 (오늘 진입종목 {len(state.daily_entered)}개)"
                    )
            if signals:
                logger.info(f"신호 발견: {len(signals)}개 — {[s.get('ticker','?') for s in signals[:5]]}")
            # 매수 고려 종목 대시보드용 저장 (스캔 직후)
            state.candidates = [
                {
                    "ticker": s["ticker"],
                    "name": _get_stock_name(s["ticker"]),
                    "rank_score": round(float(s.get("rank_score", 0)), 3),
                    "scanned_at": datetime.now().strftime("%H:%M:%S"),
                }
                for s in signals
            ]
            _save_candidates(state.candidates)

            for sig_info in signals:
                if len(state.positions) >= args.max_positions:
                    logger.debug(f"{sig_info['ticker']} 진입 스킵: max_positions 도달 ({len(state.positions)}/{args.max_positions})")
                    break

                ticker = sig_info["ticker"]
                sig    = sig_info["signal"]

                # ── windows: 시간대별 진입 top_n 제한 ────────────────────────
                _now_t = _now_hhmm()
                _cur_win = next(
                    (w for w in p.get("windows", []) if w.get("start", "") <= _now_t < w.get("end", "")),
                    None,
                )
                if _cur_win:
                    _win_n = int(_cur_win.get("top_n", 999))
                    _win_cnt = sum(
                        1 for _p in state.positions.values()
                        if _p.entry_ts and str(_p.entry_ts)[:10] == today_str
                        and _cur_win["start"] <= str(_p.entry_ts)[11:16] < _cur_win["end"]
                    )
                    if _win_cnt >= _win_n:
                        logger.info(
                            f"  [window] {ticker} 진입 스킵: "
                            f"{_cur_win['name']} top_n={_win_n} 초과 ({_win_cnt}건)"
                        )
                        continue

                # ── max_same_sector: 동일 섹터 진입 제한 ─────────────────────
                _max_sec = int(p.get("max_same_sector", 999))
                if _max_sec < 999 and sector_map:
                    _tkr_sec = sector_map.get(ticker, "")
                    if _tkr_sec:
                        _sec_cnt = sum(
                            1 for _p in state.positions.values()
                            if sector_map.get(_p.ticker, "") == _tkr_sec
                        )
                        if _sec_cnt >= _max_sec:
                            logger.info(
                                f"  [sector] {ticker} 진입 스킵: "
                                f"섹터='{_tkr_sec}' {_sec_cnt}종목 이미 보유"
                            )
                            continue

                # 현재가 조회
                cur_price = kis.get_current_price(ticker)
                entry_price = cur_price if cur_price and cur_price > 0 else sig.entry_price_est

                # entry_price 가 0/None 이면 _compute_risk_levels 가 ValueError 발생 →
                # 새 포지션을 만들지 않고 다음 후보로 진행 (기존엔 SL=0 으로 즉시 -100% 손절 위험).
                try:
                    sl_price, tp1_price, tp2_price = _compute_risk_levels(entry_price, p)
                except ValueError as _eve:
                    logger.warning(f"  {ticker} 진입 스킵 — {_eve}")
                    continue
                # 단일 TP 모드(tp1_pct=None) vs 2-tier TP 모드 분기
                if p.get("tp1_pct") is not None:
                    tp_log = f"TP1={tp1_price:.0f}  TP2={tp2_price:.0f}"
                else:
                    tp_log = f"TP={tp1_price:.0f}"

                qty_full = _calc_qty(entry_price, sl_price, args.risk_pct, kis,
                               fallback_equity=state.initial_equity)
                qty_full = _cap_qty_by_orderable_cash(entry_price, qty_full, kis)
                if qty_full <= 0:
                    if not IS_MOCK:
                        state.account_value_unknown = True
                        msg = (
                            "[SEV1] SWING-MOM account value unavailable during entry sizing; "
                            "blocking new entries until the balance API recovers."
                        )
                        logger.error(msg)
                        try:
                            if notifier:
                                notifier.send_message(msg)
                        except Exception as _ne:
                            logger.debug(f"SEV1 account-value notify failed: {_ne}")
                    logger.warning(f"  {ticker} 포지션 사이즈 0 — 계좌 조회 실패로 진입 스킵")
                    continue

                # ── 분할매수: 초기 addon_ratio 비율만 진입, 나머지는 진입가 하회 시 추가 ──
                _addon_ratio = p.get("addon_ratio", 1.0)
                qty          = max(1, round(qty_full * _addon_ratio))
                _addon_qty   = qty_full - qty if _addon_ratio < 1.0 else 0

                logger.info(
                    f"[신호] {ticker} "
                    f"진입≈{entry_price:.0f}  SL={sl_price:.0f}  "
                    f"{tp_log}  "
                    f"M={sig.m_long:.2f} S={sig.s_score:.2f} "
                    f"rank={sig.rank_score:.3f}  qty={qty}/{qty_full}"
                    + (f"  addon={_addon_qty}주 대기" if _addon_qty > 0 else "")
                )

                # 주문 직전 시간 하드 컷오프 (entry_end 이후 주문 차단)
                if _now_hhmm() >= p.get("entry_end", "14:30"):
                    logger.warning(f"  {ticker} 진입 마감({p.get('entry_end')}) 초과 — 주문 차단")
                    break

                # ── -1 호가 지정가 진입 → 60초 미체결 시 시장가 폴백 ──────
                _ask1 = kis.get_ask1(ticker)
                if _ask1 > 0:
                    _tick = kis.get_tick_size(_ask1)
                    _limit_px = _ask1 - 1 * _tick
                    logger.info(
                        f"  지정가 진입: ask1={_ask1}  tick={_tick}  "
                        f"limit={_limit_px} ({ticker})"
                    )
                    result = kis.buy_limit(ticker, qty, _limit_px)
                    if result["success"]:
                        time.sleep(60)
                        _unfilled = kis.get_unfilled_qty(result["order_no"], ticker)
                        if _unfilled > 0:
                            logger.warning(
                                f"  {ticker} 지정가 미체결({_unfilled}주) "
                                f"→ 취소 후 미체결분만 시장가 폴백"
                            )
                            _cancel_result = kis.cancel_order(
                                result["order_no"], ticker, _unfilled, _limit_px
                            )
                            # B1 fix: 미체결분만 재매수 (qty 아닌 _unfilled) — 과매수 방지
                            # 체결 합계: (qty - _unfilled) 지정가 + _unfilled 시장가 = qty. SwingPosition.qty_total = qty 유지.
                            # B2 fix: 취소 실패 시 시장가 재매수 중단 — 이중매수 방지
                            # (지정가 미취소 상태에서 시장가까지 체결되면 qty*2 매수됨)
                            if not _cancel_result.get("success"):
                                logger.error(
                                    f"  {ticker} 지정가 취소 실패 → 시장가 재매수 중단 "
                                    f"(이중매수 방지). 취소 결과: {_cancel_result.get('msg', '')}"
                                )
                                result = {"success": False, "order_no": "", "msg": "지정가 취소 실패 — 이중매수 방지를 위해 진입 중단"}
                            else:
                                result = kis.buy_market(ticker, _unfilled)
                        elif _unfilled < 0:
                            logger.warning(
                                f"  {ticker} 미체결 조회 실패 — 브로커 잔고로 체결 확인"
                            )
                            # 브로커 잔고에서 실제 보유 확인
                            _bal = kis.get_balance()
                            _held = 0
                            if _bal:
                                for _item in _bal:
                                    if _item.get("pdno") == ticker:
                                        _held = int(_item.get("hldg_qty", 0))
                                        break
                            if _held >= qty:
                                logger.info(f"  {ticker} 브로커 잔고 확인: {_held}주 보유 → 체결 인정")
                            else:
                                logger.warning(f"  {ticker} 브로커 잔고 {_held}주 < 주문 {qty}주 → 미체결 처리")
                                kis.cancel_order(result["order_no"], ticker, qty, _limit_px)
                                result = {"success": False, "msg": "미체결 확인 — 주문 취소", "order_no": ""}
                else:
                    logger.warning(f"  {ticker} ask1 조회 실패 — 시장가 폴백")
                    result = kis.buy_market(ticker, qty)
                # ───────────────────────────────────────────────────────────
                if result["success"]:
                    # 매수 체결 → candidates 에서 제거
                    state.candidates = [c for c in state.candidates if c["ticker"] != ticker]
                    _save_candidates(state.candidates)
                    # RF-005: fill price 재조회 + SL/TP 실체결가 기준 재계산
                    fill_query = kis.get_current_price(ticker)
                    _signal_px = sig.entry_price_est  # 원래 신호 추정가 (괴리 측정 기준)
                    if fill_query and fill_query > 0:
                        _fill_gap_pct = (fill_query - _signal_px) / _signal_px if _signal_px else 0.0
                        _log_level = logging.WARNING if abs(_fill_gap_pct) >= 0.01 else logging.DEBUG
                        logger.log(
                            _log_level,
                            f"  fill price: 신호추정 {_signal_px:,.0f} → 시장가 {fill_query:,.0f}원 "
                            f"(괴리 {_fill_gap_pct:+.2%})",
                        )
                        if abs(_fill_gap_pct) >= 0.01 and notifier:
                            notifier.send_message(
                                f"⚠️ [슬리피지 경고] {ticker} 신호가={_signal_px:,.0f} "
                                f"체결추정={fill_query:,.0f} 괴리={_fill_gap_pct:+.2%}\n"
                                f"SL 기준이 신호가 아닌 체결가로 재계산됩니다."
                            )
                        try:
                            sl_price, tp1_price, tp2_price = _compute_risk_levels(fill_query, p)
                            entry_price = fill_query
                        except ValueError as _eve:
                            # 재조회가 비정상이면 기존 추정 SL/TP 유지(이미 첫 호출에서 검증됨).
                            logger.warning(f"  fill price 재계산 스킵 — {_eve}")
                    else:
                        logger.warning(f"  fill price 재조회 실패 — 추정가 {entry_price:,.0f}원 유지")
                    df_5m  = today_dfs.get(ticker)
                    bar_idx = len(df_5m) - 1 if df_5m is not None else 0

                    pos = SwingPosition(
                        ticker=ticker,
                        name=_get_stock_name(ticker),
                        entry_price=entry_price,
                        sl_price=sl_price,
                        tp1_price=tp1_price,
                        tp2_price=tp2_price,
                        qty_total=qty,
                        qty_remaining=qty,
                        entry_ts=sig.signal_ts,
                        entry_bar_idx=bar_idx,
                        addon_qty=_addon_qty,
                        addon_done=(_addon_qty == 0),
                    )
                    state.positions[ticker] = pos
                    state.signal_count += 1
                    # Codex US-02: 같은 종목 일중 재진입 방지용 — 항상 기록.
                    # 옵션이 OFF 면 _check_signals 단계의 dedup 가 적용되지 않으므로 무영향.
                    state.daily_entered.add(ticker)
                    state.daily_entered_date = date.today().isoformat()
                    _save_state(state)  # RF-D7: 진입 즉시 영속화
                    logger.info(f"  매수 성공: ODNO={result['order_no']}")
                    # 대시보드 trading.db 매수 기록
                    try:
                        _journal.record_trade({
                            "code":         ticker,
                            "name":         _get_stock_name(ticker),
                            "trade_type":   "buy",
                            "decision":     "buy",
                            "price":        entry_price,
                            "qty":          qty,
                            "trigger_type": "swing_mom",
                            "source":       "swing_mom_kr",
                            "buy_rationale": (
                                f"M={sig.m_long:.2f} S={sig.s_score:.2f} "
                                f"rank={sig.rank_score:.3f}"
                            ),
                            "quant_score":  round(sig.rank_score, 4),
                            "stop_loss":    sl_price,
                            "target_price": tp1_price,
                        })
                    except Exception as _je:
                        logger.warning(f"[Journal] 매수 기록 실패: {_je}")
                    # Codex US-04: dual-write — canonical trade_events 테이블 기록.
                    try:
                        _journal.record_trade_event(TradeEvent(
                            event_ts=TradeEvent.now_ts(),
                            ticker=ticker,
                            side="BUY",
                            entry_price=float(entry_price),
                            exit_price=None,
                            qty=int(qty),
                            pnl=None,
                            pnl_pct=None,
                            reason="swing_mom",
                            source="swing_mom_kr",
                        ))
                    except Exception as _te:
                        logger.warning(f"[TradeEvent] 매수 기록 실패: {_te}")
                    notifier.send_trade_entry(
                        strategy="SWING-MOM",
                        ticker=f"{_get_stock_name(ticker)}({ticker})",
                        entry_price=entry_price,
                        sl_price=sl_price,
                        tp_price=tp1_price,
                        tp2_price=tp2_price,
                        qty=qty,
                        mode_str="[모의]" if IS_MOCK else "[실전]",
                        reason=(
                            f"모멘텀 돌파 — M={sig.m_long:.2f} "
                            f"S={sig.s_score:.2f} "
                            f"(rank={sig.rank_score:.3f})"
                        ),
                    )
                else:
                    _err_msg = (result or {}).get("msg") or (result or {}).get("message") or "unknown"
                    logger.error(f"  매수 실패: {_err_msg}")
                    # 거절도 권위 있는 이력으로 남긴다 — 사후 디버깅·게이트 분석에 필수.
                    # decision='rejected' + rejection_reason 을 명시적으로 전달 →
                    # trading_journal 이 별도 컬럼으로 저장 (buy_rationale 에만 의존 안 함).
                    try:
                        _journal.record_trade({
                            "code":             ticker,
                            "name":             _get_stock_name(ticker),
                            "trade_type":       "buy",
                            "decision":         "rejected",
                            "rejection_reason": str(_err_msg),
                            "price":            entry_price,
                            "qty":              qty,
                            "trigger_type":     "swing_mom",
                            "source":           "swing_mom_kr",
                            "buy_rationale":    f"REJECTED: {_err_msg}",
                            "quant_score":      round(sig.rank_score, 4),
                            "stop_loss":        sl_price,
                            "target_price":     tp1_price,
                        })
                    except Exception as _je:
                        logger.warning(f"[Journal] 매수 거절 기록 실패: {_je}")

        # 상태 출력
        if state.positions:
            open_pos = {t: p for t, p in state.positions.items() if p.status != "CLOSED"}
            logger.info(
                f"보유: {list(open_pos.keys())}  "
                f"오늘신호={state.signal_count}건  "
                f"일간P&L={state.daily_pnl:+,.0f}원"
            )
        time.sleep(10)

    scheduler.stop()
    logger.info(
        f"=== 종료 | 총신호={state.signal_count}건 | 일간P&L={state.daily_pnl:+,.0f}원 ==="
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        # lockfile 정리
        _lock_path = os.path.join(_ROOT, "locks", "swing_mom.lock")
        try:
            if os.path.exists(_lock_path) and open(_lock_path).read().strip() == str(os.getpid()):
                os.remove(_lock_path)
        except Exception:
            pass
