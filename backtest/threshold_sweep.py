"""
Threshold sweep - 기존 백테스트 CSV에서 GREEN 임계값을 다양하게 바꾸면서
'GREEN 시점의 +10d 평균 수익률 / 승률 / MDD / GREEN 비중'을 측정한다.

좋은 임계 = GREEN 비중이 적당(5-25%)하면서 베이스라인 대비 +10d, 승률, MDD가 명확히 우월.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
CSV = _HERE / "reports" / "entry_timing_2026-05-13.csv"

df = pd.read_csv(CSV)
print(f"loaded {len(df):,} obs from {CSV.name}")

ALL = dict(
    avg10=df["fwd10"].mean() * 100,
    win10=(df["fwd10"] > 0).mean() * 100,
    mdd=df["mdd20"].mean() * 100,
)
print(f"\nBaseline (ALL):  +10d={ALL['avg10']:+.2f}%  win={ALL['win10']:.1f}%  MDD={ALL['mdd']:.2f}%\n")


def sweep(score_col: str, label: str):
    print(f"=== {label} ===")
    print(f"{'thr':>4}  {'n':>7}  {'비중':>5}  {'+10d':>7}  {'승률':>5}  {'MDD':>7}  {'edge':>6}")
    for thr in range(40, 91, 5):
        sub = df[df[score_col] >= thr]
        if len(sub) < 100:
            continue
        avg10 = sub["fwd10"].mean() * 100
        win = (sub["fwd10"] > 0).mean() * 100
        mdd = sub["mdd20"].mean() * 100
        share = len(sub) / len(df) * 100
        edge = avg10 - ALL["avg10"]
        print(f"{thr:>4}  {len(sub):>7,}  {share:>4.1f}%  {avg10:>+6.2f}%  {win:>4.1f}%  {mdd:>+6.2f}%  {edge:>+5.2f}%")
    print()


sweep("score_new", "NEW (베이스 55, RSI 55-70 가점)")
sweep("score_old", "OLD (베이스 50, 평균회귀 편향)")

# 추가: 점수대별 버킷 (e.g. 50-55, 55-60, ...)
def buckets(score_col: str, label: str):
    print(f"=== {label} - 점수대별 버킷 ===")
    print(f"{'range':>10}  {'n':>7}  {'비중':>5}  {'+10d':>7}  {'승률':>5}  {'MDD':>7}")
    edges = list(range(0, 101, 5))
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = df[(df[score_col] >= lo) & (df[score_col] < hi)]
        if len(sub) < 100:
            continue
        avg10 = sub["fwd10"].mean() * 100
        win = (sub["fwd10"] > 0).mean() * 100
        mdd = sub["mdd20"].mean() * 100
        share = len(sub) / len(df) * 100
        print(f"{lo:>3}~{hi:<3}  {len(sub):>7,}  {share:>4.1f}%  {avg10:>+6.2f}%  {win:>4.1f}%  {mdd:>+6.2f}%")
    print()


buckets("score_new", "NEW")
buckets("score_old", "OLD")

# 최적 (hi, lo) 조합 - 3등급으로 갈랐을 때 GREEN > YELLOW > RED 단조성 + 명확한 edge
print("=== 3-grade 단조성 탐색 (NEW 점수 기준) ===")
print(f"{'hi':>3} {'lo':>3}  {'G_share':>7} {'G_+10d':>7} {'Y_+10d':>7} {'R_+10d':>7}  {'단조':>4}")
best = []
for hi in range(55, 86, 5):
    for lo in range(35, hi, 5):
        g = df[df["score_new"] >= hi]
        y = df[(df["score_new"] >= lo) & (df["score_new"] < hi)]
        r = df[df["score_new"] < lo]
        if min(len(g), len(y), len(r)) < 500:
            continue
        ga = g["fwd10"].mean() * 100
        ya = y["fwd10"].mean() * 100
        ra = r["fwd10"].mean() * 100
        mono = ga > ya > ra
        edge = ga - ra
        if mono:
            best.append((hi, lo, edge, len(g) / len(df) * 100, ga, ya, ra))
        flag = "✓" if mono else "✗"
        print(f"{hi:>3} {lo:>3}  {len(g)/len(df)*100:>6.1f}% {ga:>+6.2f}% {ya:>+6.2f}% {ra:>+6.2f}%  {flag}")

print("\n=== 단조성 만족하면서 edge(G-R) 큰 순 ===")
for hi, lo, edge, share, ga, ya, ra in sorted(best, key=lambda x: -x[2])[:8]:
    print(f"  hi={hi} lo={lo}  G비중={share:.1f}%  +10d G={ga:+.2f}% Y={ya:+.2f}% R={ra:+.2f}%  edge={edge:+.2f}%")

print("\n=== OLD 기준 단조성 탐색 ===")
best_old = []
for hi in range(55, 86, 5):
    for lo in range(35, hi, 5):
        g = df[df["score_old"] >= hi]
        y = df[(df["score_old"] >= lo) & (df["score_old"] < hi)]
        r = df[df["score_old"] < lo]
        if min(len(g), len(y), len(r)) < 500:
            continue
        ga = g["fwd10"].mean() * 100
        ya = y["fwd10"].mean() * 100
        ra = r["fwd10"].mean() * 100
        mono = ga > ya > ra
        edge = ga - ra
        if mono:
            best_old.append((hi, lo, edge, len(g) / len(df) * 100, ga, ya, ra))

for hi, lo, edge, share, ga, ya, ra in sorted(best_old, key=lambda x: -x[2])[:8]:
    print(f"  hi={hi} lo={lo}  G비중={share:.1f}%  +10d G={ga:+.2f}% Y={ya:+.2f}% R={ra:+.2f}%  edge={edge:+.2f}%")
