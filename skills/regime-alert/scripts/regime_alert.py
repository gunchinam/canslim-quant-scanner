#!/usr/bin/env python3
"""
레짐 기반 포지션 권고 → 텔레그램 알림

종료 코드:
  0 — 레짐 유지 (포지션 변동 없음)
  1 — Bull 전환  → 풀시드
  2 — Bear 전환  → 전액 현금
  3 — Chop 전환  → 50% 축소
"""
from __future__ import annotations

import json
import logging
import os
import sys

import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from regime_classifier import R_BEAR, R_BULL, R_CHOP, get_market_regime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_PREV_REGIME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".prev_regime.json")

# 레짐별 설정
_REGIME_EMOJI  = {R_BULL: "🟢", R_BEAR: "🔴", R_CHOP: "🟡"}
_REGIME_NAME   = {R_BULL: "Bull (저변동 상승)", R_BEAR: "Bear (고변동 하락)", R_CHOP: "Chop (횡보)"}
_POSITION      = {R_BULL: "풀시드  100%", R_BEAR: "현금    0%", R_CHOP: "절반    50%"}
_EXIT_CODE     = {R_BULL: 1, R_BEAR: 2, R_CHOP: 3}


def _load_prev_regime() -> str | None:
    try:
        with open(_PREV_REGIME_FILE, "r") as f:
            return json.load(f).get("state")
    except Exception:
        return None


def _save_prev_regime(state: str) -> None:
    try:
        with open(_PREV_REGIME_FILE, "w") as f:
            json.dump({"state": state}, f)
    except Exception:
        pass


def build_message(result, prev_state: str | None) -> tuple[str, int]:
    cur   = result.state
    conf  = result.probs.get(cur, 0.0)
    p_next = result.p_next

    changed    = (prev_state is not None) and (prev_state != cur)
    exit_code  = _EXIT_CODE[cur] if changed else 0

    sig        = result.transition_signal
    early_exit = bool(sig.get("early_exit", False))
    early_long = bool(sig.get("early_long", False))
    strength   = float(sig.get("strength", 0.0))

    lines: list[str] = []

    # ── 헤더: 레짐 전환 or 유지 ──────────────────────────────
    if changed:
        prev_emoji = _REGIME_EMOJI.get(prev_state, "⚪")
        cur_emoji  = _REGIME_EMOJI[cur]
        lines += [
            f"🔔 *레짐 전환*  {prev_emoji} → {cur_emoji}",
            f"*{_REGIME_NAME[cur]}*",
            "",
        ]
    else:
        lines += [
            f"{_REGIME_EMOJI[cur]} *KOSPI 레짐 브리핑*",
            f"*{_REGIME_NAME[cur]}* 유지",
            "",
        ]

    # ── 포지션 권고 (핵심) ────────────────────────────────────
    lines += [
        f"📌 *권고 포지션: {_POSITION[cur]}*",
        f"확신도 {conf:.0%}  |  모델: {result.model_status}",
        "",
    ]

    # ── 내일 예측 확률 ────────────────────────────────────────
    lines += [
        "내일 레짐 확률",
        f"  🟢 Bull  {p_next.get(R_BULL, 0):.0%}",
        f"  🔴 Bear  {p_next.get(R_BEAR, 0):.0%}",
        f"  🟡 Chop  {p_next.get(R_CHOP, 0):.0%}",
    ]

    # ── early 신호 (보조) ─────────────────────────────────────
    if early_exit:
        lines += ["", f"⚡ 선행 신호: Bear 압력 상승 중 (강도 {strength:.0%})"]
    elif early_long:
        lines += ["", f"⚡ 선행 신호: Bull 전환 가능성 상승 중 (강도 {strength:.0%})"]

    return "\n".join(lines), exit_code


def send_telegram(message: str) -> bool:
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("TELEGRAM 미설정 — 콘솔 출력")
        sys.stdout.buffer.write((message + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()
    log.info("텔레그램 발송 완료")
    return True


def main() -> int:
    log.info("레짐 분석 시작 (KOSPI ^KS11)")
    result     = get_market_regime("KR")
    prev_state = _load_prev_regime()

    log.info("state=%s prev=%s conf=%.2f model=%s",
             result.state, prev_state,
             result.probs.get(result.state, 0), result.model_status)

    message, exit_code = build_message(result, prev_state)
    send_telegram(message)

    _save_prev_regime(result.state)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
