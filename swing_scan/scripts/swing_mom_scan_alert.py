"""swing_scan/scripts/swing_mom_scan_alert.py
SWING-MOM 신호 스캔 전용 텔레그램 알리미 (자동매매 없음)

종목스캐너 프로젝트 내 자체 완결형.
live_swing_mom_trader.py 와 동일한 LIVE_PARAMS / 유니버스 / 신호 로직을 사용하되,
주문 실행 없이 텔레그램으로 신호만 전송한다.

실행 (종목스캐너 루트에서):
  py -3 swing_scan/scripts/swing_mom_scan_alert.py
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Set

# swing_scan 패키지 루트를 sys.path 에 추가
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SWING_SCAN_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _SWING_SCAN_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

if getattr(sys.stdout, "buffer", None) is not None:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )
if getattr(sys.stderr, "buffer", None) is not None:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )

# 로그 디렉토리는 swing_scan 내부에 생성
_LOG_DIR = os.path.join(_SWING_SCAN_ROOT, "logs")
Path(_LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(_LOG_DIR, f"scan_alert_{date.today().isoformat()}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

# .env 로드 (swing_scan 루트의 .env)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(_SWING_SCAN_ROOT, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

# live trader 헬퍼 함수 재사용
import live_swing_mom_trader as trader

from execution.kis_client import get_client
from utils.telegram_notifier import get_notifier


def main():
    parser = argparse.ArgumentParser(description="SWING-MOM 스캔 전용 알리미 (자동매매 없음)")
    parser.add_argument("--universe_n", type=int, default=50,
                        help="거래대금 상위 N종목 (기본 50)")
    parser.add_argument("--data_dir",
                        default=os.path.join(_SWING_SCAN_ROOT, "data", "minute"))
    parser.add_argument("--daily_dir",
                        default=os.path.join(_SWING_SCAN_ROOT, "data", "daily"))
    args = parser.parse_args()

    # 스캔 전용: entry_start 를 09:00 으로 오버라이드
    p = {**trader.LIVE_PARAMS, "entry_start": "09:00"}

    logger.info("=== SWING-MOM 스캔 알리미 시작 (자동매매 OFF) ===")
    logger.info(f"유니버스={args.universe_n}종목, 스캔시간={p['entry_start']}~{p['entry_end']}")

    # ── 텔레그램 스팸 방지: 시장 시간 외 / 주말 시작 시 알림 발송 금지 ──
    # 이유: web_app 가 부팅·재시작마다 _start_swing_scanner() 호출 → 시장외에서도
    # "[시작]/[종료]" 2건씩 텔레그램 발송. (2026-05-15 23시 다중 재시작 확인)
    _now_dt = datetime.now()
    _now_hhmm = _now_dt.strftime("%H:%M")
    _is_weekend = _now_dt.weekday() >= 5  # 5=Sat 6=Sun
    _in_window = (p["entry_start"] <= _now_hhmm < "15:30") and not _is_weekend
    if not _in_window:
        logger.info(
            f"스캔 윈도우 외(now={_now_hhmm}, weekend={_is_weekend}) — "
            "텔레그램 발송 없이 즉시 종료"
        )
        return

    today_str = date.today().isoformat()
    kis = get_client()
    notifier = get_notifier()

    # KIS 토큰 확보
    for attempt in range(1, 4):
        try:
            kis.get_access_token()
            logger.info(f"KIS API 연결 성공 (시도 {attempt}/3)")
            break
        except Exception as e:
            logger.warning(f"KIS API 연결 실패 시도 {attempt}/3: {e}")
            if attempt == 3:
                logger.error("KIS API 연결 최종 실패 — 종료")
                return
            time.sleep(10)

    # 유니버스 구성
    all_tickers = trader._collect_tickers(args.data_dir)
    tickers = trader._top_n_by_volume(all_tickers, args.daily_dir, n=args.universe_n)
    if not tickers:
        try:
            boot, _ = trader._fetch_volume_rank(kis, n=args.universe_n)
            if boot:
                tickers = list(boot)
        except Exception:
            pass
    if not tickers:
        logger.error("유니버스 확보 불가 — 종료")
        return

    liq_scores = trader._liq_scores(tickers, args.daily_dir)
    sector_map = trader._load_sector_map(args.data_dir)
    logger.info(f"초기 유니버스: {len(tickers)}종목")

    # 인덱스 히스토리 백필
    trader._backfill_index_hist(kis, args.data_dir, "069500", days=10)

    # 빈 TradingState (포지션 없음 = 모든 종목 스캔 가능)
    state = trader.TradingState()

    context_map: dict = trader._load_context_cache(today_str)
    last_bar = ""
    last_ctx_bar = ""
    prev_alert_tickers: Set[str] = set()

    start_sent = False
    if notifier and notifier.is_enabled():
        notifier.send_message(
            f"<b>[스캔 알리미 시작]</b>\n"
            f"유니버스 {len(tickers)}종목 | {p['entry_start']}~{p['entry_end']}\n"
            f"자동매매 OFF — 신호 알림만 전송합니다."
        )
        start_sent = True

    logger.info(f"대기 중... ({p['entry_start']} 스캔 시작)")

    while True:
        now = trader._now_hhmm()
        now_dt = datetime.now()

        # 장 시작 전 대기
        if now < p["entry_start"]:
            time.sleep(30)
            continue

        # 15:30 이후 종료
        if now >= "15:30":
            logger.info("장 마감 — 스캔 종료")
            break

        # entry_end 이후 스캔 중지
        if now >= p["entry_end"]:
            logger.info(f"{p['entry_end']} 스캔 마감 — 종료 대기")
            time.sleep(60)
            continue

        # 5분봉 완성 시점 감지
        min_mod = now_dt.minute % 5
        if min_mod != 0 or now_dt.strftime("%H:%M") == last_bar:
            time.sleep(10)
            continue

        current_bar = now_dt.strftime("%H:%M")
        last_bar = current_bar
        logger.info(f"--- {current_bar} 스캔 ---")

        # 유니버스 갱신
        new_tickers, new_scores = trader._fetch_volume_rank(kis, n=args.universe_n)
        if new_tickers:
            tickers = new_tickers
            liq_scores = new_scores

        # 5분봉 로드
        today_dfs = trader._load_today_5m(
            tickers, args.data_dir, today_str,
            kis_client=kis, current_hhmm=current_bar,
        )
        if not today_dfs:
            logger.warning("5분봉 데이터 없음")
            time.sleep(30)
            continue
        logger.info(f"5분봉 로드: {len(today_dfs)}/{len(tickers)}종목")

        # 인덱스(069500) 별도 fetch
        if "069500" not in today_dfs:
            import polars as pl
            for _retry in range(3):
                idx_bars = trader._fetch_kis_5m(kis, "069500")
                if idx_bars:
                    today_dfs["069500"] = trader._filter_today_until_bar(
                        trader._resample_to_5m(pl.DataFrame(idx_bars)),
                        today_str, current_bar,
                    )
                    break
                time.sleep(2)

        # context_map 재빌드
        _early = now_dt.hour < 10
        _need_rebuild = (
            _early
            or now_dt.minute % 30 == 0
            or not context_map
            or not any(k[1].startswith(today_str) for k in context_map)
        )
        if current_bar != last_ctx_bar and _need_rebuild:
            logger.info("context_map 재빌드 중...")
            try:
                new_ctx = trader._build_context_map(
                    tickers, today_dfs, args.data_dir,
                    liq_scores, sector_map, today_str,
                )
                if new_ctx:
                    context_map = new_ctx
            except Exception as e:
                logger.warning(f"context_map 빌드 실패: {e}")
            last_ctx_bar = current_bar
            logger.info(f"context_map: {len(context_map)}개 항목")

        if not context_map:
            logger.warning("context_map 비어있음 — 스캔 불가")
            continue

        # 신호 스캔 (빈 state = 포지션 없으므로 모든 종목 스캔)
        logger.info(f"신호 스캔: {len(tickers)}종목 (context {len(context_map)}개)")
        signals = trader._check_signals(
            tickers, today_dfs, context_map, state, current_bar, p,
            today_str=today_str,
        )

        if not signals:
            logger.info("신호 없음")
            prev_alert_tickers.clear()
            continue

        # 중복 알림 방지: 이전 bar 와 동일 종목이면 스킵
        cur_tickers = {s["ticker"] for s in signals}
        new_tickers_detected = cur_tickers - prev_alert_tickers
        prev_alert_tickers = cur_tickers

        if not new_tickers_detected:
            logger.info(f"기존 신호 유지 ({len(signals)}종목) — 중복 알림 스킵")
            continue

        # 텔레그램 알림 전송 (기존 send_watchlist_briefing 포맷)
        logger.info(
            f"신호 {len(signals)}개 (신규 {len(new_tickers_detected)}개): "
            f"{[s['ticker'] for s in signals[:5]]}"
        )
        if notifier and notifier.is_enabled():
            candidates = []
            for s in signals:
                sig = s["signal"]
                ticker = s["ticker"]
                candidates.append({
                    "ticker": ticker,
                    "name": trader._get_stock_name(ticker),
                    "rank_score": sig.rank_score,
                    "m_score": sig.m_long,
                    "s_score": sig.s_score,
                })
            notifier.send_watchlist_briefing(
                candidates=candidates,
                strategy="SWING-MOM [스캔전용]",
                open_positions=0,
                max_positions=0,
            )
            logger.info("텔레그램 알림 전송 완료")
        else:
            logger.warning("텔레그램 미설정 — 알림 전송 불가")

    if start_sent and notifier and notifier.is_enabled():
        notifier.send_message("<b>[스캔 알리미 종료]</b> 장 마감")
    logger.info("=== 스캔 알리미 종료 ===")


if __name__ == "__main__":
    main()
