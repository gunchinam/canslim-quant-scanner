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


import re as _re

# 일반 풀(_PHRASES)은 종목 데이터를 안 보고 해시로 뽑힌다.
# 따라서 특정 사실(테마/섹터/실적/수치/기술적)을 단정하면 그 종목엔
# 거짓이 된다. 일반 풀은 polarity 톤만 담고, 검증된 단정은 _METRIC_PHRASES만.
_FORBIDDEN_GENERIC = _re.compile(
    r"정치\s*테마|정책\s*테마|양자컴|2차전지|메타버스|필수소비재"
    r"|유틸리티\s*종목|규제\s*산업|경기방어주"
    r"|코스피\s*\d{3,}|코스닥\s*\d{3,}|베타\s*0|샤프비율|VIX"
    r"|RSI\s*\d|PER\s*\d|PBR\s*\d|ROE\s*\d+\s*%|배당\s*\d|부채비율\s*\d"
    r"|거래량\s*\d+\s*배|골든크로스|데드크로스|볼린저밴드|일목균형표"
    r"|어닝\s*서프라이즈|추정치\s*상[향회]|적자\s*전환|자본\s*잠식"
    r"|상장폐지|거래정지|유상증자"
)


def test_generic_pools_have_no_unverified_assertions():
    offenders = []
    for bucket, lst in ol._PHRASES.items():
        for p in lst:
            if _FORBIDDEN_GENERIC.search(p):
                offenders.append((bucket, p))
    assert not offenders, (
        "일반 풀에 검증 불가 단정이 남아있음: "
        + "; ".join(f"{b}:{p}" for b, p in offenders[:10])
    )


def test_generic_pools_variety_and_no_dupes():
    # 사용자 요구: "다양하게 나오게" — 버킷당 충분한 풀 + 중복 없음
    for bucket, lst in ol._PHRASES.items():
        assert len(lst) >= 60, f"{bucket}: 풀이 {len(lst)}개뿐 (>=60 필요)"
        assert len(lst) == len(set(lst)), f"{bucket}: 중복 문구 존재"
        for p in lst:
            assert not p.rstrip().endswith("."), f"{bucket}: 마침표로 끝남 -> {p}"


def test_no_period_in_metric_pools():
    for key, lst in ol._METRIC_PHRASES.items():
        for p in lst:
            assert not p.rstrip().endswith("."), f"{key}: 마침표로 끝남 -> {p}"


# 사용자 요구: "문구를 기술적인 건 쓰지말고 주갤형식으로만 평가하는걸로 해."
# 일반 풀과 데이터 게이트 풀(_METRIC_PHRASES) 둘 다 순수 주갤 구어체만 남고
# 애널리스트/차트 전문용어는 한 단어도 남으면 안 된다.
# 슬랭(1등/반토막/한 방/존버/줍줍 등)은 허용 — 단어 기반 매칭이라 오검출 없음.
_FORBIDDEN_TECH = _re.compile(
    r"RSI|MACD|볼린저|일목|스토캐스틱|이격도|ADX|엘리엇|피보나치"
    r"|이평선|이동평균|골든크로스|데드크로스|다이버전스"
    r"|PER|PBR|PSR|PEG|ROE|ROA|ROIC|WACC|EBITDA"
    r"|밸류에이션|밸류|멀티플|베타|변동성|드로다운|MDD|샤프|VIX|표준편차"
    r"|펀더멘탈|펀더|어닝|컨센서스|가이던스|추정치|EPS|영업이익률|마진율"
    r"|부채비율|현금흐름|FCF|모멘텀|과매수|과매도|변곡점|신고가|신저가"
    r"|배당수익률|시가총액|시총|디스카운트|괴리율|괴리|리레이팅|안전마진"
    r"|청산가치|양봉|음봉|거래량|지지선|업사이드|목표가|숏스퀴즈|숏커버"
    r"|서프라이즈|트리거|시그널"
    r"|\d+\s*%|\d+\s*프로|한\s*자릿수|두\s*자릿수"
)


def test_no_technical_jargon_anywhere():
    offenders = []
    for bucket, lst in ol._PHRASES.items():
        for p in lst:
            m = _FORBIDDEN_TECH.search(p)
            if m:
                offenders.append(("GEN", bucket, m.group(0), p))
    for key, lst in ol._METRIC_PHRASES.items():
        k = "|".join(key) if isinstance(key, tuple) else key
        for p in lst:
            m = _FORBIDDEN_TECH.search(p)
            if m:
                offenders.append(("MET", k, m.group(0), p))
    assert not offenders, (
        "기술 용어가 남아있음 (순수 주갤만 허용): "
        + "; ".join(f"{pl}/{b}[{t}]:{p}" for pl, b, t, p in offenders[:15])
    )


class _UT(unittest.TestCase):
    def test_all(self):
        test_score_grade_thresholds()
        test_weak_score_blocks_strong_positive()
        test_consistency_cases()
        test_high_score_never_negative_oneliner_sweep()
        test_low_score_never_positive_oneliner_sweep()
        test_generic_pools_have_no_unverified_assertions()
        test_generic_pools_variety_and_no_dupes()
        test_no_period_in_metric_pools()
        test_no_technical_jargon_anywhere()


if __name__ == "__main__":
    unittest.main()
