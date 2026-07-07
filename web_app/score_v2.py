"""score_v2.py — 횡단면 표준화 순위 (Barra/Grinold-Kahn 스타일)

팩터별 winsorize(MAD ±3σ) → 횡단면 z-score → 가중합 → 백분위(0~100)를
RankPct 필드로 병기한다. TotalScore/Signal(절대 품질 축)은 건드리지 않는다
— 백분위가 TotalScore를 덮어쓰면 시그널 사다리·등급·임계값이 전부 고정
비율 컷으로 변질되고 캡/감쇄 패치가 무력화되기 때문 (2026-07-07 이원화).

- TotalScore: legacy 절대 점수 (판단 축 — "오늘 살까?")
- RankPct:    오늘 유니버스 내 순위 백분위 (탐색 축 — "무엇부터 볼까?")
- _LegacyScore: 스냅샷 legacy 계열 연속성 유지용 (forward IC ablation)

env SCORE_V2=0 → no-op (RankPct 미산출, 원클릭 롤백).
"""
from __future__ import annotations

import os

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
        r["RankPct"] = round(float(sc), 1)
