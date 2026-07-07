"""score_ablation.py — ScoreV2 vs Legacy vs 팩터군 forward IC 비교 CLI.

사용: python score_ablation.py --market KR --horizon 10 [--min-days 5]
스냅샷(history)에 기록된 TotalScore/legacy/factors를 point-in-time으로 읽어
forward N거래일 수익률과의 Spearman IC를 날짜별 계산 → Newey-West/부트스트랩 집계.
출력: 콘솔 표 + cache_v19/score_ablation_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_app"))

from regime_ic import _spearman, _nw_tstat, _block_bootstrap_ci  # noqa: E402

GROUPS = {
    "mid_momentum": ("momentum", "rs"),
    "st_reversal":  ("st_rev_5d",),
    "near_high":    ("near_52w",),
    "flow":         ("volume", "smart_money"),
    "quality":      ("quality", "fama_french"),
    "tech_setup":   ("mtf", "bb_revert", "orb", "nr7"),
}


def group_score(factors: dict, group: str) -> float:
    members = GROUPS[group]
    vals = [float(factors.get(m, 0.0) or 0.0) for m in members]
    return sum(vals) / len(vals)


def cross_sectional_ic(scores: dict, fwd_returns: dict):
    """공통 티커의 Spearman IC. 표본<8이면 None."""
    import numpy as np
    common = [t for t in scores if t in fwd_returns
              and scores[t] is not None and fwd_returns[t] is not None]
    if len(common) < 8:
        return None
    a = np.array([scores[t] for t in common], dtype=float)
    b = np.array([fwd_returns[t] for t in common], dtype=float)
    return _spearman(a, b)


def load_snapshots(market: str) -> dict:
    """{date: {ticker: row}} — history 스냅샷 디렉터리에서 로드."""
    import history
    out = {}
    snap_dir = history._SNAP_DIR
    prefix = f"scanner_{market}_"
    for name in sorted(os.listdir(snap_dir)):
        if not (name.startswith(prefix) and name.endswith(".json")):
            continue
        d = name[len(prefix):-5]
        try:
            with open(os.path.join(snap_dir, name), encoding="utf-8") as f:
                out[d] = json.load(f)
        except Exception:
            continue
    return out


def fetch_forward_returns(tickers: list, start: str, horizon: int) -> dict:
    """yfinance 일봉으로 start 이후 horizon 거래일 수익률."""
    import yfinance as yf
    out = {}
    try:
        df = yf.download(tickers, start=start, progress=False,
                         group_by="ticker", threads=False)
    except Exception:
        return out
    for t in tickers:
        try:
            closes = (df[t]["Close"] if len(tickers) > 1 else df["Close"]).dropna()
            if len(closes) > horizon:
                out[t] = float(closes.iloc[horizon] / closes.iloc[0] - 1.0)
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="KR")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--min-days", type=int, default=5)
    args = ap.parse_args()

    snaps = load_snapshots(args.market)
    variants = ["v2", "legacy"] + list(GROUPS)
    ics: dict[str, list] = {v: [] for v in variants}
    usable_days = 0

    for d, snap in snaps.items():
        rows = {t: r for t, r in snap.items()
                if isinstance(r, dict) and not r.get("missing") and r.get("factors")}
        if len(rows) < 8:
            continue
        fwd = fetch_forward_returns(list(rows), d, args.horizon)
        if len(fwd) < 8:
            continue
        usable_days += 1
        day_scores = {
            # 신포맷(2026-07-07 이원화 이후): v2 필드 = RankPct 백분위.
            # 구포맷(~07-07, score가 백분위였던 시기): legacy 필드 존재가 v2 실행 마커.
            "v2":     {t: r.get("v2", r.get("score") if "legacy" in r else None)
                       for t, r in rows.items()},
            "legacy": {t: r.get("legacy") for t, r in rows.items()},
            **{g: {t: group_score(r["factors"], g) for t, r in rows.items()}
               for g in GROUPS},
        }
        for v in variants:
            ic = cross_sectional_ic(day_scores[v], fwd)
            if ic is not None:
                ics[v].append(ic)

    report = {"market": args.market, "horizon": args.horizon,
              "usable_days": usable_days, "generated": datetime.now().isoformat(),
              "results": {}}
    print(f"\n=== Score Ablation IC (market={args.market}, h={args.horizon}d, days={usable_days}) ===")
    if usable_days < args.min_days:
        print(f"INSUFFICIENT: 사용 가능 스냅샷 {usable_days}일 < 최소 {args.min_days}일")
        report["status"] = "INSUFFICIENT"
    else:
        report["status"] = "OK"
        for v in variants:
            xs = ics[v]
            if len(xs) < 3:
                report["results"][v] = {"n": len(xs), "status": "INSUFFICIENT"}
                print(f"{v:>14}: n={len(xs)} INSUFFICIENT")
                continue
            mean_ic = sum(xs) / len(xs)
            t = _nw_tstat(xs, lag=max(1, args.horizon // 2))
            lo, hi = _block_bootstrap_ci(xs, block=max(2, args.horizon // 2))
            report["results"][v] = {"n": len(xs), "mean_ic": round(mean_ic, 4),
                                    "t_stat": round(t, 2), "ci95": [round(lo, 4), round(hi, 4)]}
            print(f"{v:>14}: IC={mean_ic:+.4f}  t={t:+.2f}  CI95=[{lo:+.4f},{hi:+.4f}]  n={len(xs)}")

    out_path = os.path.join("cache_v19", "score_ablation_report.json")
    os.makedirs("cache_v19", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nreport → {out_path}")


if __name__ == "__main__":
    main()
