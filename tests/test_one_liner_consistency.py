"""Regression tests: 점수 등급 ↔ 한줄평 톤 일관성.

별점/상태(TotalScore) · 진입 타이밍(EntryStatus) · 한줄평(_bucket)이
서로 다른 이야기를 하던 미스매치 버그의 재발을 막는다.

규칙:
  - score >= 72  → 한줄평은 긍정 톤이어야 한다 (진입 타이밍이 AVOID여도)
  - score <  35  → 한줄평은 부정 톤이어야 한다 (강한 팩터가 있어도)
  - 35 <= score < 48 → 강한 긍정(STRONG_BUY/BREAKOUT) 금지
  - 48 <= score < 72 → 강한 부정(AVOID/FALLING_KNIFE/VALUE_TRAP/BUBBLE) 금지

Uses pytest if available; otherwise falls back to unittest.
No external network calls.
"""

from __future__ import annotations

import os
import sys
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_WEB_APP = os.path.join(_PROJECT_ROOT, "web_app")
for _p in (_PROJECT_ROOT, _WEB_APP):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import one_liner as ol  # noqa: E402


def _polarity(bucket: str) -> str:
    if bucket in ol._POS_BUCKETS:
        return "pos"
    if bucket in ol._NEG_BUCKETS:
        return "neg"
    return "neu"


# (이름, 종목 dict, 기대 톤)
_CASES = [
    # 고득점 + 진입 AVOID — 예전 버그: AVOID 한줄평이 별 4개와 모순
    ("high_score_entry_avoid",
     {"Ticker": "AAA", "TotalScore": 91, "EntryStatus": "AVOID",
      "Drawdown": -0.05, "_Mom3M": 2, "IsLeader": True}, "pos"),
    # 고득점인데 폴백 NEUTRAL 로 빠지던 케이스
    ("high_score_fallback_neutral",
     {"Ticker": "BBB", "TotalScore": 78, "Mom12M": 0.25}, "pos"),
    # ⭐⭐ 경계 (72) — 긍정이어야
    ("leader_boundary_72",
     {"Ticker": "BB2", "TotalScore": 72, "EntryStatus": "AVOID",
      "Drawdown": -0.10, "_Mom3M": -3}, "pos"),
    # 저득점인데 강한 팩터로 긍정 버킷 → 부정으로 정렬
    ("low_score_strong_factors",
     {"Ticker": "CCC", "TotalScore": 22, "EntryStatus": "STRONG",
      "NearHighPass": True, "Mom12M": 0.4}, "neg"),
    # 관망 구간 + 원시 강부정 → 중립으로 완화
    ("solid_score_raw_negative",
     {"Ticker": "DDD", "TotalScore": 55, "EntryStatus": "AVOID",
      "Drawdown": -0.30, "_Mom3M": -10}, "neu"),
    # 진짜 나쁜 종목은 그대로 부정
    ("truly_bad_stays_negative",
     {"Ticker": "EEE", "TotalScore": 18, "EntryStatus": "AVOID",
      "Drawdown": -0.4, "_Mom3M": -12}, "neg"),
    # 진짜 좋은 종목은 그대로 긍정
    ("truly_good_stays_positive",
     {"Ticker": "FFF", "TotalScore": 88, "EntryStatus": "STRONG",
      "NearHighPass": True, "Mom12M": 0.45, "IsLeader": True}, "pos"),
]


def _check(name, d, want):
    bucket = ol._bucket(d)
    got = _polarity(bucket)
    assert got == want, (
        f"{name}: score={d.get('TotalScore')} "
        f"raw={ol._raw_bucket(d)} -> {bucket} ({got}), want {want}"
    )


def test_score_grade_thresholds():
    assert ol._score_grade(72) == "STRONG"
    assert ol._score_grade(71.9) == "SOLID"
    assert ol._score_grade(48) == "SOLID"
    assert ol._score_grade(47) == "WEAK"
    assert ol._score_grade(35) == "WEAK"
    assert ol._score_grade(34) == "AVOID"


def test_weak_score_blocks_strong_positive():
    # 35~47 구간: 강한 긍정 버킷 금지
    d = {"Ticker": "WK1", "TotalScore": 40, "EntryStatus": "STRONG",
         "NearHighPass": True, "Mom12M": 0.5, "IsLeader": True}
    assert ol._bucket(d) not in ("STRONG_BUY", "BREAKOUT", "SECTOR_LEADER")


def test_consistency_cases():
    for name, d, want in _CASES:
        _check(name, d, want)


def test_high_score_never_negative_oneliner_sweep():
    # 72점 이상이면 어떤 진입상태/팩터 조합에서도 부정 톤이 나오면 안 된다
    for score in (72, 80, 90, 99):
        for entry in ("AVOID", "NEUTRAL", "STRONG", "RED", "GREEN"):
            d = {"Ticker": "SWP", "TotalScore": score, "EntryStatus": entry,
                 "Drawdown": -0.35, "_Mom3M": -12, "_PER": 90, "RSI": 80}
            b = ol._bucket(d)
            assert b not in ol._NEG_BUCKETS, (
                f"score={score} entry={entry} -> {b} (부정 톤 금지)"
            )


def test_low_score_never_positive_oneliner_sweep():
    # 35점 미만이면 어떤 조합에서도 긍정 톤이 나오면 안 된다
    for score in (0, 10, 25, 34):
        for entry in ("STRONG", "GREEN", "NEUTRAL"):
            d = {"Ticker": "SWN", "TotalScore": score, "EntryStatus": entry,
                 "NearHighPass": True, "Mom12M": 0.6, "IsLeader": True,
                 "EPSAcceleration": True}
            b = ol._bucket(d)
            assert b not in ol._POS_BUCKETS, (
                f"score={score} entry={entry} -> {b} (긍정 톤 금지)"
            )


class _UT(unittest.TestCase):
    def test_all(self):
        test_score_grade_thresholds()
        test_weak_score_blocks_strong_positive()
        test_consistency_cases()
        test_high_score_never_negative_oneliner_sweep()
        test_low_score_never_positive_oneliner_sweep()


if __name__ == "__main__":
    unittest.main()
