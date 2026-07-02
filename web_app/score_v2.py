"""score_v2.py — 횡단면 표준화 점수 (Barra/Grinold-Kahn 스타일)

팩터별 winsorize(MAD ±3σ) → 횡단면 z-score → 가중합 → 백분위(0~100).
게이트(적자·저유동성·MDD·약세장)는 점수 변조 대신 RiskFlags 기반 시그널 강등.
시장 전역 승수(VIX·매크로·BearCap)는 순위를 못 바꾸므로 점수에서 제외.

env SCORE_V2=0 → no-op (legacy TotalScore 유지, 원클릭 롤백).
"""
from __future__ import annotations

import os
import re

import numpy as np

# ── 팩터군 가중치 (설계 스펙 표) — 군 내부 균등 분할 ──
FACTOR_GROUPS: dict[str, tuple[float, tuple[str, ...]]] = {
    "mid_momentum": (0.25, ("momentum", "rs")),
    "st_reversal":  (0.15, ("st_rev_5d",)),
    "near_high":    (0.15, ("near_52w",)),
    "flow":         (0.15, ("volume", "smart_money")),
    "quality":      (0.15, ("quality", "fama_french")),
    "tech_setup":   (0.15, ("mtf", "bb_revert", "orb", "nr7")),
}
MIN_SAMPLE = 10

# 시그널 사다리 — 기존 STEP 11 임계 유지 (fulfilled 조건은 v2에서 미사용 → 82 상한)
_LADDER = [
    (82, "⭐⭐⭐ STRONG LEADER"),
    (72, "⭐⭐ LEADER"),
    (60, "⭐ WATCH LIST — Accumulate"),
    (48, "⏸ NEUTRAL — Hold"),
    (35, "⚠️ CAUTION — Reduce"),
    (0,  "📉 SELL / AVOID"),
]
# RiskFlags → 시그널 상한 점수 (사다리 기준값)
_FLAG_CAPS = {
    "LOW_LIQUIDITY": 60,   # 최대 WATCH
    "MDD_HIGH":      60,
    "MDD_EXTREME":   48,   # 최대 HOLD
    "EPS_NEGATIVE":  48,
    "RS_LAGGARD":    35,
    "BEAR_MARKET":   48,
}
_SUFFIX_RE = re.compile(r"\s(?:🔔)?\[")


def _winsorize_z(col: np.ndarray) -> np.ndarray:
    """MAD 기반 ±3σ winsorize 후 z-score. 상수 열이면 0."""
    med = float(np.median(col))
    mad = float(np.median(np.abs(col - med)))
    sigma = 1.4826 * mad
    if sigma > 0:
        col = np.clip(col, med - 3 * sigma, med + 3 * sigma)
    mean, std = float(col.mean()), float(col.std())
    if std <= 1e-12:
        return np.zeros_like(col)
    return (col - mean) / std


def _label(score: float) -> str:
    for th, lbl in _LADDER:
        if score >= th:
            return lbl
    return _LADDER[-1][1]


def _legacy_suffix(sig: str) -> str:
    """기존 Signal의 부가 태그([BREAKOUT], [EPS🔥] 등) 보존."""
    m = _SUFFIX_RE.search(sig or "")
    return sig[m.start():] if m else ""


def apply_score_v2(rows: list) -> None:
    if os.environ.get("SCORE_V2", "1").strip() in ("0", "false", "no"):
        return
    items = [r for r in rows if isinstance(r, dict) and isinstance(r.get("_Factors"), dict)]
    if len(items) < MIN_SAMPLE:
        return

    # 팩터 행렬 구성 — 결측 팩터는 0(중립)
    keys = sorted({k for r in items for k in r["_Factors"]})
    mat = np.array([[float(r["_Factors"].get(k, 0.0) or 0.0) for k in keys] for r in items])
    zmat = np.column_stack([_winsorize_z(mat[:, j]) for j in range(mat.shape[1])])
    zmap = {k: zmat[:, j] for j, k in enumerate(keys)}

    combined = np.zeros(len(items))
    for _g, (w, members) in FACTOR_GROUPS.items():
        avail = [m for m in members if m in zmap]
        if not avail:
            continue
        each = w / len(members)
        for m in avail:
            combined += each * zmap[m]

    order = combined.argsort().argsort()  # 0..n-1 순위
    pct = order / max(1, len(items) - 1) * 100.0

    for r, sc in zip(items, pct):
        if "_LegacyScore" not in r and isinstance(r.get("TotalScore"), (int, float)):
            r["_LegacyScore"] = float(r["TotalScore"])
        score = round(float(sc), 1)
        # RiskFlags 시그널 강등 — 점수는 순수 순위 유지
        cap = min((_FLAG_CAPS[f] for f in (r.get("RiskFlags") or []) if f in _FLAG_CAPS),
                  default=None)
        label_score = score if cap is None else min(score, cap)
        legacy_sig = r.get("Signal") or ""
        r["_LegacySignal"] = legacy_sig
        r["Signal"] = _label(label_score) + _legacy_suffix(legacy_sig)
        r["TotalScore"] = score
