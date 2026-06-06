# -*- coding: utf-8 -*-
"""fundamental_value_grade.py — 재무가치 등급 (횡단면 백분위 합성).

Phase 1 (네이버 데이터만, 무료 60% → 100% 재정규화):
    성장 QoQ 3종(매출·영업이익·순이익) + ROE + PBR + PSR.
    YoY 블록·OCF·PEGR 은 DART 연동 후 Phase 2 에서 추가(게이트).

설계 원칙 (월가 퀀트 패널 리뷰 반영):
    - 방향성: ROE·성장 = 정순 / PBR·PSR(·PEGR) = 역순(저평가=고득점).
    - 결측(None): 해당 종목 비중을 가용 지표로 재정규화 → 0점 왜곡 방지.
    - 백분위 랭크는 magnitude 에 robust → 분모효과 outlier 가 순위를 지배하지 않음.
      (분모 0/음수·부호전환으로 정의가 깨진 성장률은 데이터 계층에서 None 으로 넘긴다.)
    - basis="universe"(전체종목) / "sector"(섹터내) 두 버전을 동일 함수로 산출 → IC 비교용.

순수 함수 — 네트워크/IO 없음.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

# Phase 1 가중치 (원안 60% 부분을 100%로 재정규화: 성장 25% + ROE/PBR/PSR 각 25%).
# Phase 2 에서 YoY·OCF·PEGR 합류 시 원안 20/20/60 으로 복원 예정.
DEFAULT_WEIGHTS: dict[str, float] = {
    "rev_qoq": 0.0833,   # 매출 QoQ 성장률
    "op_qoq":  0.0833,   # 영업이익 QoQ 성장률
    "ni_qoq":  0.0834,   # 순이익 QoQ 성장률
    "roe":     0.25,
    "pbr":     0.25,
    "psr":     0.25,
}

# 낮을수록 좋은 지표 — 백분위를 역순(1 - pct)으로 점수화.
INVERTED_METRICS: frozenset[str] = frozenset({"pbr", "psr", "pegr"})


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """ticker→값 dict 를 cross-sectional 백분위(0.0~1.0)로. 동률은 평균 rank.

    표본 1개면 순위 불가 → 중립(0.5).
    """
    if not values:
        return {}
    items = sorted(values.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 1:
        return {items[0][0]: 0.5}
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        pct = ((i + j) / 2.0) / (n - 1)
        for k in range(i, j + 1):
            ranks[items[k][0]] = pct
        i = j + 1
    return ranks


def compute_grades(
    records: Iterable[dict[str, Any]],
    *,
    basis: str = "universe",
    weights: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """종목별 재무가치 등급(0~100)을 횡단면 백분위로 산출.

    Args:
        records: 종목별 dict 리스트. 필수 키 ``ticker``, ``sector``.
            지표 키(``DEFAULT_WEIGHTS`` 의 키)는 float 또는 None(결측).
        basis: "universe"(전체종목 백분위) | "sector"(섹터내 백분위).
        weights: 지표→가중치. 미지정 시 ``DEFAULT_WEIGHTS``.

    Returns:
        ``{ticker: {"grade": float, "percentiles": {metric: score}, "basis": str}}``
    """
    w = dict(weights or DEFAULT_WEIGHTS)
    metrics = list(w.keys())
    recs = list(records)

    def group_of(rec: dict[str, Any]) -> str:
        return str(rec.get("sector", "")) if basis == "sector" else "__ALL__"

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in recs:
        groups[group_of(rec)].append(rec)

    # (metric → ticker → 방향성 보정된 점수[0..1])
    metric_score: dict[str, dict[str, float]] = {m: {} for m in metrics}
    for grp in groups.values():
        for m in metrics:
            vals: dict[str, float] = {}
            for rec in grp:
                v = rec.get(m)
                if v is None:
                    continue
                try:
                    vals[str(rec["ticker"])] = float(v)
                except (TypeError, ValueError):
                    continue
            for t, p in _percentiles(vals).items():
                metric_score[m][t] = (1.0 - p) if m in INVERTED_METRICS else p

    out: dict[str, dict[str, Any]] = {}
    for rec in recs:
        t = str(rec["ticker"])
        num = 0.0
        wsum = 0.0
        comp: dict[str, float] = {}
        for m in metrics:
            if t in metric_score[m]:
                s = metric_score[m][t]
                num += s * w[m]
                wsum += w[m]
                comp[m] = round(s, 6)
        grade = (num / wsum) * 100.0 if wsum > 0 else 50.0  # 가용 지표 전무 → 중립
        out[t] = {"grade": round(grade, 4), "percentiles": comp, "basis": basis}
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """단순 Pearson 상관 (numpy 비의존). 표본<3 또는 무분산이면 None."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def apply_grades(
    results: list[dict[str, Any]],
    *,
    quarter_fetch,
    ttm_fetch=None,
    weights: dict[str, float] | None = None,
    log=None,
) -> dict[str, Any]:
    """스캔 결과(dict 리스트)에 재무가치 등급을 부여하고 기존 팩터와의 상관을 계측.

    각 result dict 에 다음 키를 in-place 추가:
        ``FinValue``    전체종목 백분위 등급(0~100) 또는 None(데이터 결측)
        ``FinValueSec`` 섹터내 백분위 등급(0~100) 또는 None

    Args:
        results: 스캔 결과. 각 dict 필수 키 ``Ticker``; 선택 ``Sector``,
            ``_MarketCap``, ``_PBR``, ``ValueScore``, ``QualityScore``.
        quarter_fetch: ``fn(code)->dict`` (naver_quarter.get_quarter_metrics 호환).
        ttm_fetch: ``fn(code)->dict`` (revenue 제공). PSR 산출용. None 이면 PSR 생략.
        weights: compute_grades 가중치 오버라이드.
        log: ``fn(str)`` 진행 로그 콜백(선택).

    Returns:
        상관 요약 ``{"n", "pearson_value", "pearson_quality"}``.
    """
    records: list[dict[str, Any]] = []
    graded_tickers: list[str] = []
    for r in results:
        ticker = str(r.get("Ticker", ""))
        if not ticker:
            r["FinValue"] = None
            r["FinValueSec"] = None
            continue
        code = ticker.split(".")[0]
        try:
            q = quarter_fetch(code) or {}
        except Exception:
            q = {}
        if not q.get("available"):
            r["FinValue"] = None
            r["FinValueSec"] = None
            continue

        # PSR = 시가총액 / TTM 매출 (낮을수록 저평가)
        psr = None
        if ttm_fetch is not None:
            try:
                rev = float((ttm_fetch(code) or {}).get("revenue") or 0)
            except Exception:
                rev = 0.0
            mc = float(r.get("_MarketCap") or 0)
            if rev > 0 and mc > 0:
                psr = mc / rev

        pbr = q.get("pbr")
        if pbr is None:
            _p = r.get("_PBR")
            pbr = float(_p) if _p else None

        records.append({
            "ticker": ticker,
            "sector": r.get("Sector", ""),
            "rev_qoq": q.get("rev_qoq"),
            "op_qoq": q.get("op_qoq"),
            "ni_qoq": q.get("ni_qoq"),
            "roe": q.get("roe"),
            "pbr": pbr,
            "psr": psr,
        })
        graded_tickers.append(ticker)

    if not records:
        if log:
            log("[FinValue] 등급 부여 가능한 종목 없음 (데이터 결측)")
        return {"n": 0, "pearson_value": None, "pearson_quality": None}

    g_uni = compute_grades(records, basis="universe", weights=weights)
    g_sec = compute_grades(records, basis="sector", weights=weights)

    by_ticker = {str(r.get("Ticker", "")): r for r in results}
    for t in graded_tickers:
        r = by_ticker.get(t)
        if r is None:
            continue
        r["FinValue"] = round(g_uni[t]["grade"], 1)
        r["FinValueSec"] = round(g_sec[t]["grade"], 1)

    # ── 기존 팩터와의 상관 계측 (직교성 점검) ──
    fv, vs, qs = [], [], []
    for t in graded_tickers:
        r = by_ticker.get(t)
        if r is None:
            continue
        fv.append(r["FinValue"])
        vs.append(float(r.get("ValueScore", 0) or 0))
        qs.append(float(r.get("QualityScore", 0) or 0))
    p_val = _pearson(fv, vs)
    p_qual = _pearson(fv, qs)
    if log:
        def _fmt(x):
            return f"{x:+.2f}" if x is not None else "N/A"
        log(f"[FinValue] {len(graded_tickers)}종목 등급 부여 · "
            f"기존 ValueScore 상관 {_fmt(p_val)} · QualityScore 상관 {_fmt(p_qual)}")
    return {"n": len(graded_tickers), "pearson_value": p_val, "pearson_quality": p_qual}
