# 점수 파이프라인 수정·재구축·검증·종가베팅 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TotalScore를 단기 스윙 수익률 예측 목적에 맞게 버그 수정(A) → 횡단면 표준화 ScoreV2 재구축(B) → forward IC 검증 하니스(C) → 종가베팅 leading signal의 market-aware 실시간화(D).

**Architecture:** 종목별 팩터 산출(기존 `_analyze_ticker` 재사용, `_Factors`/`RiskFlags` 기록)과 횡단면 결합(신규 `web_app/score_v2.py`, winsorize→z-score→가중합→백분위)의 2단 분리. 기존 점수는 `_LegacyScore`로 병행 기록, env `SCORE_V2=0` 롤백. 스펙: `docs/superpowers/specs/2026-07-02-score-pipeline-fixes-design.md`

**Tech Stack:** Python 3.x, numpy, pytest, Flask, yfinance. 신규 외부 의존성 금지.

## Global Constraints

- 플랫폼: Windows (경로 구분자 주의), 리포 루트 = `C:\Users\new123\Documents\카카오톡 받은 파일\종목스캐너`
- 테스트 실행: 리포 루트에서 `python -m pytest tests/<file> -v`
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 주석은 기존 스타일대로 한국어. 신규 외부 패키지 추가 금지(numpy/pandas/yfinance 기존 사용분만).
- 네트워크를 쓰는 테스트 금지 — 전부 모킹/고정 입력.
- 파일 인코딩 UTF-8.

---

### Task 1: A-1 드로다운 게이트 무효화 수정

**Files:**
- Modify: `quant_nexus_v20.py` (CANSLIM dict ~:688 인근, 5전략 루프 :6182 인근)
- Test: `tests/test_score_fixes.py` (신규)

**Interfaces:**
- Produces: `CANSLIM["DD_MULT_EXTREME"]=0.65`, `CANSLIM["DD_MULT_HIGH"]=0.80` — Task 4·6에서 같은 dict 스타일 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_score_fixes.py` 생성:

```python
"""Phase A 버그 수정 검증 — 네트워크 없이 코드 구조/함수 단위 검증."""
import re


def _src():
    with open("quant_nexus_v20.py", encoding="utf-8") as f:
        return f.read()


def test_dd_mult_constants_exist():
    src = _src()
    assert '"DD_MULT_EXTREME"' in src
    assert '"DD_MULT_HIGH"' in src


def test_dd_gate_applied_inside_strategy_loop():
    """5전략 루프(all_scores 채우는 for문) 안에 드로다운 감쇄가 있어야 한다."""
    src = _src()
    loop_start = src.index("for _i, _mode in enumerate(_SW_MODES):")
    loop_end = src.index("all_scores[_mode] = round(_f, 1)")
    loop_body = src[loop_start:loop_end]
    assert "_dd_risk" in loop_body, "5전략 루프에 드로다운 게이트 미적용 (composite가 STEP10.6을 덮어씀)"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_score_fixes.py -v`
Expected: 2건 FAIL (`DD_MULT_EXTREME` 미존재, 루프 내 `_dd_risk` 부재)

- [ ] **Step 3: 구현**

(1) `quant_nexus_v20.py` CANSLIM dict의 `"BEAR_CAP": 0.50,` 라인 앞에 추가:

```python
    "DD_MULT_EXTREME":   0.65,   # MDD 극단 낙폭 감쇄 승수 (STEP 10.6 / 5전략 루프 공용)
    "DD_MULT_HIGH":      0.80,   # MDD 고위험 낙폭 감쇄 승수
```

(2) STEP 10.6(:6125-6133)의 하드코딩 `0.65`/`0.80`을 `CANSLIM["DD_MULT_EXTREME"]`/`CANSLIM["DD_MULT_HIGH"]`로 교체. `_dd_risk = dd.get("risk", "NORMAL")` 라인은 STEP 10.6 위치 그대로 유지(루프에서 재사용).

(3) 5전략 루프 내 `if low_liquidity: _f = min(_f, 55.0)` (:6182-6183) 바로 아래에 추가:

```python
                # 드로다운 게이트 — STEP 10.6과 동일 감쇄를 5전략 경로에도 적용
                # (composite가 final을 덮어써 STEP 10.6이 무효화되던 버그 수정)
                if _dd_risk == "EXTREME":
                    _f *= CANSLIM["DD_MULT_EXTREME"]
                elif _dd_risk == "HIGH":
                    _f *= CANSLIM["DD_MULT_HIGH"]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_score_fixes.py -v` → PASS
Run: `python -c "import ast; ast.parse(open('quant_nexus_v20.py', encoding='utf-8').read())"` → 무출력(구문 OK)

- [ ] **Step 5: Commit**

```bash
git add quant_nexus_v20.py tests/test_score_fixes.py
git commit -m "fix(score): 드로다운 게이트 무효화 수정 — 5전략 루프에 MDD 감쇄 적용"
```

---

### Task 2: A-2 MoatBonus 멱등화

**Files:**
- Modify: `web_app/app.py:200-205` (`_apply_moat_bonus`), `web_app/app.py:443-457` (`_annotate_moats` force 분기)
- Test: `tests/test_score_fixes.py` (추가)

**Interfaces:**
- Produces: row 필드 `_MoatApplied: bool` — 적용 완료 마커. Task 7의 score_v2는 이 필드를 건드리지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_score_fixes.py`에 추가:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))


def test_moat_bonus_idempotent():
    from app import _apply_moat_bonus
    rows = [{"Ticker": "T", "TotalScore": 70.0, "MoatBonus": 5}]
    _apply_moat_bonus(rows)
    assert rows[0]["TotalScore"] == 75.0
    _apply_moat_bonus(rows)  # 2회째 — 누적되면 안 됨
    assert rows[0]["TotalScore"] == 75.0, "MoatBonus 이중 가산"
```

주의: `from app import` 가 무거우면(부작용) `import app` 실패 시 이 테스트에서 원인 파악 — app.py는 import 시 서버를 띄우지 않아야 정상(기존 `if __name__` 가드 확인).

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_score_fixes.py::test_moat_bonus_idempotent -v`
Expected: FAIL (75 → 80으로 누적)

- [ ] **Step 3: 구현** — `web_app/app.py`:

```python
def _apply_moat_bonus(rows: list) -> None:
    """MoatBonus를 TotalScore에 반영한다. 모든 캐시 저장 경로에서 호출.
    _MoatApplied 마커로 멱등 보장 — 같은 리스트가 여러 경로를 거쳐도 1회만 가산."""
    for r in rows:
        if not isinstance(r, dict) or r.get("_MoatApplied"):
            continue
        bonus = r.get("MoatBonus", 0)
        if bonus and isinstance(r.get("TotalScore"), (int, float)):
            r["TotalScore"] = min(100.0, r["TotalScore"] + bonus)
            r["_MoatApplied"] = True
```

그리고 `_annotate_moats`의 force 분기(`r.pop("Moat", None)` 등 3개 pop이 있는 곳)에 `r.pop("_MoatApplied", None)` 추가.

- [ ] **Step 4: 테스트 통과 확인** — Run: `python -m pytest tests/test_score_fixes.py -v` → 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add web_app/app.py tests/test_score_fixes.py
git commit -m "fix(score): MoatBonus 멱등화 — 8개 호출 경로 이중 가산 차단"
```

---

### Task 3: A-3 midcap_alpha moat 이중 반영 제거

**Files:**
- Modify: `web_app/engine_adapter.py:292-304` (`_attach_midcap_alpha`)
- Test: `tests/test_score_fixes.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def test_midcap_alpha_no_moat_double_count():
    from engine_adapter import _attach_midcap_alpha
    base = {"Indices": ["SP400"], "TotalScore": 70, "RSRating": 80,
            "_MarketCap": 9e9, "_VolRatio": 1.0, "_EPS": 1.0}
    r_moat = dict(base, MoatBonus=3)
    r_plain = dict(base, MoatBonus=0)
    _attach_midcap_alpha([r_moat]); _attach_midcap_alpha([r_plain])
    # moat 기여는 ts를 통해서만 — promo 직접 가산이 없어야 동일
    assert r_moat["MidcapPromotion"] == r_plain["MidcapPromotion"], "moat 이중 반영"
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_score_fixes.py::test_midcap_alpha_no_moat_double_count -v` → FAIL (moat*5=15 차이)

- [ ] **Step 3: 구현** — `engine_adapter.py:304`:

```python
        promo = min(100, round(mcap_prox + profit + rs_part))
```

(`+ min(15, moat * 5)` 항 삭제. `moat = r.get("MoatBonus") or 0` 라인(:297)도 미사용이 되므로 삭제.)

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: Commit**

```bash
git add web_app/engine_adapter.py tests/test_score_fixes.py
git commit -m "fix(score): midcap_alpha promo의 moat 이중 반영 제거"
```

---

### Task 4: A-4 슈퍼그로스 승수 명명 상수화 (죽은 상수 제거)

**Files:**
- Modify: `quant_nexus_v20.py:686-687` (CANSLIM dict), `:6088-6104` (STEP 9)
- Test: `tests/test_score_fixes.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def test_super_mult_constants_replace_dead_ones():
    src = _src()
    assert '"SUPER_MULT_MIN"' not in src, "죽은 상수 잔존"
    assert '"SUPER_MULT_MAX"' not in src
    for k in ('"SUPER_MULT_ACCEL"', '"SUPER_MULT_STRONG"',
              '"SUPER_MULT_HIGH52"', '"SUPER_MULT_FULL"', '"SUPER_MULT_PARTIAL"'):
        assert k in src, f"{k} 명명 상수 부재"
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — CANSLIM dict :686-687 두 줄을 다음으로 교체:

```python
    "SUPER_MULT_ACCEL":   1.18,  # C+A+L 완전충족 + EPS 가속
    "SUPER_MULT_STRONG":  1.14,  # C+A+L 완전충족 + EPS 강한 성장
    "SUPER_MULT_HIGH52":  1.10,  # C+A+L 완전충족 + 신고가·거래량 확인
    "SUPER_MULT_FULL":    1.07,  # C+A+L 완전충족 (기타)
    "SUPER_MULT_PARTIAL": 1.05,  # 2/3 충족
```

STEP 9(:6088-6104)의 리터럴 `1.18/1.14/1.10/1.07/1.05`를 각각 `CANSLIM["SUPER_MULT_ACCEL"]` 등으로 교체.

- [ ] **Step 4: 통과 + 구문 확인** — pytest PASS, `python -c "import ast; ast.parse(open('quant_nexus_v20.py', encoding='utf-8').read())"` OK
- [ ] **Step 5: Commit**

```bash
git add quant_nexus_v20.py tests/test_score_fixes.py
git commit -m "refactor(score): 슈퍼그로스 승수 명명 상수화 — 죽은 SUPER_MULT_MIN/MAX 제거"
```

---

### Task 5: A-5 스테일 캐시 점수 감쇄

**Files:**
- Modify: `quant_nexus_v20.py:5362-5377` (stale 폴백 블록)
- Test: `tests/test_score_fixes.py` (추가)

**Interfaces:**
- Produces: row 필드 `StaleDays: int`, `_RawTotalScore: float`(감쇄 전 원본). Task 9의 스냅샷이 이 필드를 이용 가능.

- [ ] **Step 1: 감쇄 로직을 순수 함수로 분리하는 테스트 작성**:

```python
def test_stale_penalty():
    import quant_nexus_v20 as qn
    row = {"TotalScore": 80.0}
    out = qn._apply_stale_penalty(dict(row), days_back=3)
    assert out["TotalScore"] == 71.0          # 80 - 3*3
    assert out["_RawTotalScore"] == 80.0
    assert out["StaleDays"] == 3
    out0 = qn._apply_stale_penalty(dict(row), days_back=0)
    assert out0["TotalScore"] == 80.0 and out0["StaleDays"] == 0
    out9 = qn._apply_stale_penalty(dict(row), days_back=9)
    assert out9["TotalScore"] == 65.0          # min(15, 27) 캡
```

- [ ] **Step 2: 실패 확인** → FAIL (`_apply_stale_penalty` 미정의)

- [ ] **Step 3: 구현** — `quant_nexus_v20.py`의 `DataCache` 클래스 정의 아래(모듈 레벨)에 추가:

```python
def _apply_stale_penalty(row: dict, days_back: int) -> dict:
    """스테일 캐시 점수 감쇄 — 하루당 3점, 최대 15점. 원본은 _RawTotalScore 보존."""
    row["StaleDays"] = int(days_back)
    ts = row.get("TotalScore")
    if days_back > 0 and isinstance(ts, (int, float)):
        row.setdefault("_RawTotalScore", float(ts))
        row["TotalScore"] = max(0.0, float(ts) - min(15.0, 3.0 * days_back))
    return row
```

stale 폴백 블록(:5362-5377)을 다음으로 교체 — days_back 추적 추가:

```python
            if hist is None or hist.empty or len(hist) < 30:
                # 오늘 날짜 키로 먼저 조회, 없으면 최대 7일 이전 키까지 lookback
                stale = self.cache.get(strategy_key, max_age_minutes=60 * 24 * 30)
                _stale_days = 0
                if not stale:
                    for _days_back in range(1, 8):
                        _prev = (datetime.now() - timedelta(days=_days_back)).strftime("%Y%m%d")
                        _prev_key = f"{ticker}__{self._scan_strategy}__{_prev}"
                        stale = self.cache.get(_prev_key, max_age_minutes=60 * 24 * (_days_back + 1))
                        if stale:
                            _stale_days = _days_back
                            break
                if stale:
                    stale = dict(stale)
                    stale.setdefault("DataSource", "cache")
                    stale.setdefault("DataStatus", "STALE_CACHE")
                    return _apply_stale_penalty(stale, _stale_days)
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: Commit**

```bash
git add quant_nexus_v20.py tests/test_score_fixes.py
git commit -m "fix(score): 스테일 캐시 점수 감쇄 — 하루당 3점(최대 15), StaleDays 기록"
```

---

### Task 6: B-1 `_Factors` + `RiskFlags` 기록

**Files:**
- Modify: `quant_nexus_v20.py` (`_fv_arr` 구성 직후 :6148 인근, result dict :6833 인근)
- Test: `tests/test_score_v2.py` (신규)

**Interfaces:**
- Produces: row 필드 `_Factors: dict[str, float]` — 키는 `_SW_KEYS`의 23개 팩터명(momentum, fama_french, mean_reversion, quality, regime, smart_money, mtf, drawdown, volume, rs, price_target, short_int, math, sentiment, cs_c, cs_a, cs_n, cs_s, cs_l, cs_i, orb, nr7, bb_revert) + `st_rev_5d`(5일 수익률 역방향) + `near_52w`(1−신고가거리). row 필드 `RiskFlags: list[str]` — 값 ∈ {EPS_NEGATIVE, RS_LAGGARD, LOW_LIQUIDITY, MDD_EXTREME, MDD_HIGH, BEAR_MARKET}. Task 7·9가 소비.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_score_v2.py` 생성:

```python
"""ScoreV2 — 팩터 기록/횡단면 결합 검증 (네트워크 불요)."""


def _src():
    with open("quant_nexus_v20.py", encoding="utf-8") as f:
        return f.read()


def test_factors_and_riskflags_recorded_in_result():
    src = _src()
    assert '"_Factors":' in src, "_analyze_ticker result에 _Factors 부재"
    assert '"RiskFlags":' in src, "_analyze_ticker result에 RiskFlags 부재"
    assert '"st_rev_5d"' in src and '"near_52w"' in src
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현**

(1) `_fv_arr` 구성 직후(:6148의 `], dtype=np.float64)` 다음 줄)에 추가:

```python
            # ── ScoreV2 팩터 기록 — 횡단면 표준화(score_v2.py)의 입력 ──
            _factor_map = {k: round(float(v), 3) for k, v in zip(_SW_KEYS, _fv_arr)}
            try:
                _factor_map["st_rev_5d"] = round(
                    -float(hist["Close"].iloc[-1] / hist["Close"].iloc[-6] - 1.0), 4
                ) if len(hist) >= 6 else 0.0
            except Exception:
                _factor_map["st_rev_5d"] = 0.0
            _factor_map["near_52w"] = round(1.0 - float(mom.get("dist_from_52w_high", 1.0)), 4)
            _risk_flags: list = []
            if earn["fail_safe_eps"]: _risk_flags.append("EPS_NEGATIVE")
            if rs["fail_safe_rs"]:    _risk_flags.append("RS_LAGGARD")
            if low_liquidity:         _risk_flags.append("LOW_LIQUIDITY")
            if _dd_risk == "EXTREME": _risk_flags.append("MDD_EXTREME")
            elif _dd_risk == "HIGH":  _risk_flags.append("MDD_HIGH")
            if bear_cap_applied:      _risk_flags.append("BEAR_MARKET")
```

(2) result dict의 `"TotalScore": final,` 라인 바로 아래에 추가:

```python
                "_Factors":         _factor_map,
                "RiskFlags":        _risk_flags,
```

(3) `web_app/app.py:185`의 `_SCAN_STRIP_FIELDS`는 변경하지 않는다(경량 스칼라라 응답 포함 허용 — Breakdown/Scores만 계속 제거).

- [ ] **Step 4: 통과 + 구문 확인** → PASS + ast.parse OK
- [ ] **Step 5: Commit**

```bash
git add quant_nexus_v20.py tests/test_score_v2.py
git commit -m "feat(score-v2): _Factors 25종 + RiskFlags 기록 — 횡단면 표준화 입력 준비"
```

---

### Task 7: B-2 `score_v2.py` 횡단면 표준화 모듈

**Files:**
- Create: `web_app/score_v2.py`
- Test: `tests/test_score_v2.py` (추가)

**Interfaces:**
- Consumes: Task 6의 `_Factors`, `RiskFlags`.
- Produces: `apply_score_v2(rows: list[dict]) -> None` — 각 row의 `TotalScore`를 백분위 점수로 교체, `_LegacyScore`(원본), `Signal` 재산정. env `SCORE_V2=0`이면 no-op. 표본 <10이면 no-op.

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def _mkrow(i, mom, rev, q):
    return {"Ticker": f"T{i}", "TotalScore": 50.0, "Signal": "⏸ NEUTRAL — Hold",
            "RiskFlags": [],
            "_Factors": {"momentum": mom, "rs": mom, "st_rev_5d": rev,
                         "near_52w": 0.5, "volume": 50, "smart_money": 50,
                         "quality": q, "fama_french": q,
                         "mtf": 50, "bb_revert": 50, "orb": 0, "nr7": 0}}


def test_apply_score_v2_percentile():
    import os
    os.environ.pop("SCORE_V2", None)
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, mom=float(i * 10), rev=0.0, q=50.0) for i in range(12)]
    apply_score_v2(rows)
    scores = [r["TotalScore"] for r in rows]
    assert scores == sorted(scores), "모멘텀 단조증가 → 점수 단조증가여야"
    assert all(0 <= s <= 100 for s in scores)
    assert rows[0]["_LegacyScore"] == 50.0


def test_apply_score_v2_small_sample_noop():
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, 10.0, 0.0, 50.0) for i in range(5)]
    apply_score_v2(rows)
    assert all(r["TotalScore"] == 50.0 for r in rows), "표본<10 → 변경 금지"


def test_apply_score_v2_riskflag_signal_cap():
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, float(i * 10), 0.0, 50.0) for i in range(12)]
    rows[-1]["RiskFlags"] = ["MDD_EXTREME"]
    apply_score_v2(rows)
    assert "⏸" in rows[-1]["Signal"] or "📉" in rows[-1]["Signal"], "MDD_EXTREME → HOLD 이하로 강등"


def test_apply_score_v2_env_off():
    import os
    os.environ["SCORE_V2"] = "0"
    try:
        from score_v2 import apply_score_v2
        rows = [_mkrow(i, float(i * 10), 0.0, 50.0) for i in range(12)]
        apply_score_v2(rows)
        assert all(r["TotalScore"] == 50.0 for r in rows)
    finally:
        os.environ.pop("SCORE_V2", None)
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_score_v2.py -v` → import error FAIL

- [ ] **Step 3: 구현** — `web_app/score_v2.py` 생성:

```python
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
        label_score = score if cap is None else min(score, cap - 0.1)
        legacy_sig = r.get("Signal") or ""
        r["_LegacySignal"] = legacy_sig
        r["Signal"] = _label(label_score) + _legacy_suffix(legacy_sig)
        r["TotalScore"] = score
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_score_v2.py -v` → 전부 PASS
- [ ] **Step 5: Commit**

```bash
git add web_app/score_v2.py tests/test_score_v2.py
git commit -m "feat(score-v2): 횡단면 winsorize→z-score→가중합→백분위 점수 모듈"
```

---

### Task 8: B-3 스캔 경로에 ScoreV2 연결

**Files:**
- Modify: `web_app/engine_adapter.py` (`scan_sector` :714-724, `scan_all` 결과 조립부 — `results.sort(key=_scan_sort_key, reverse=True)` 직전 두 곳)
- Test: `tests/test_score_v2.py` (추가)

**Interfaces:**
- Consumes: Task 7 `apply_score_v2`.

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def test_engine_adapter_wires_score_v2():
    with open("web_app/engine_adapter.py", encoding="utf-8") as f:
        src = f.read()
    assert src.count("apply_score_v2(results)") >= 2, "scan_sector/scan_all 양쪽 연결 필요"
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `engine_adapter.py`의 `scan_sector`와 `scan_all` 각각에서 `results.sort(key=_scan_sort_key, reverse=True)` **직전**에 삽입:

```python
        # ScoreV2 — 횡단면 표준화 점수 (성공/실패와 무관하게 스캔은 계속)
        try:
            from score_v2 import apply_score_v2
            apply_score_v2(results)
        except Exception as _sve:
            logging.warning("score_v2 적용 실패 (legacy 점수 유지): %s", _sve)
```

(모든 `_attach_*` 호출 이후 = moat·regime 부착 뒤, 정렬 직전. `_scan_sort_key`는 TotalScore/RegimeEntryScore를 읽으므로 v2 반영 순서로 정렬된다.)

- [ ] **Step 4: 통과 확인** → PASS. 추가로 `python -c "import sys; sys.path.insert(0,'web_app'); import score_v2"` OK
- [ ] **Step 5: Commit**

```bash
git add web_app/engine_adapter.py tests/test_score_v2.py
git commit -m "feat(score-v2): scan_all/scan_sector에 횡단면 점수 연결 (SCORE_V2=0 롤백 가능)"
```

---

### Task 9: C-1 스냅샷에 팩터·레거시 점수 기록

**Files:**
- Modify: `web_app/history.py:108-124` (`save_snapshot`의 `_row`)
- Test: `tests/test_ablation.py` (신규)

**Interfaces:**
- Produces: 스냅샷 row에 `factors: dict`, `legacy: float`, `flags: list` (있을 때만 — 기존 포맷 호환). Task 10이 소비.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_ablation.py` 생성:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))


def test_snapshot_row_includes_factors():
    import history
    r = {"Ticker": "AAA", "TotalScore": 88.0, "EntryStatus": "GO",
         "_Factors": {"momentum": 50.0}, "_LegacyScore": 72.0, "RiskFlags": ["LOW_LIQUIDITY"]}
    d = history._row_for_test(r)
    assert d["factors"] == {"momentum": 50.0}
    assert d["legacy"] == 72.0
    assert d["flags"] == ["LOW_LIQUIDITY"]
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `history.py`의 `_row` 내부(regime 필드 블록 뒤)에 추가:

```python
        # ScoreV2 검증용 필드 (있을 때만 — 기존 포맷 100% 호환)
        f = r.get("_Factors")
        if isinstance(f, dict) and f:
            d["factors"] = f
        leg = r.get("_LegacyScore")
        if leg is not None:
            d["legacy"] = round(float(leg), 1)
        flags = r.get("RiskFlags")
        if flags:
            d["flags"] = flags
        return d
```

`_row`는 `save_snapshot` 내부의 클로저이므로, 테스트 접근용으로 모듈 레벨 헬퍼를 추가하고 클로저가 그것을 호출하게 리팩터:

```python
def _row_for_test(r: dict, rank: int = 1) -> dict:
    """save_snapshot._row와 동일 로직 — 단위 테스트 접근용."""
    ...  # 기존 _row 본문을 이 함수로 이동, save_snapshot에서는 _row_for_test(r, rank) 호출
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: Commit**

```bash
git add web_app/history.py tests/test_ablation.py
git commit -m "feat(ablation): 스냅샷에 factors/legacy/flags 기록 — forward IC 검증 재료"
```

---

### Task 10: C-2 `score_ablation.py` forward IC 하니스

**Files:**
- Create: `score_ablation.py` (리포 루트)
- Test: `tests/test_ablation.py` (추가)

**Interfaces:**
- Consumes: `web_app/history.py`의 스냅샷 파일(`cache_v19/history/scanner_{market}_{YYYY-MM-DD}.json` — 정확한 경로는 `history._snap_path` 참조), `regime_ic._spearman/_nw_tstat/_block_bootstrap_ci`.
- Produces: CLI `python score_ablation.py --market KR --horizon 10` → 콘솔 표 + `cache_v19/score_ablation_report.json`.

- [ ] **Step 1: 실패하는 테스트 작성** (IC 계산 순수 함수만 — 네트워크 없는 부분):

```python
def test_ablation_ic_computation():
    import score_ablation as sa
    # 점수가 forward 수익과 완전 단조 → IC=1.0
    scores = {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0,
              "F": 60.0, "G": 70.0, "H": 80.0, "I": 90.0, "J": 95.0}
    fwd = {t: s / 100.0 for t, s in scores.items()}
    ic = sa.cross_sectional_ic(scores, fwd)
    assert ic is not None and abs(ic - 1.0) < 1e-9


def test_ablation_group_score():
    import score_ablation as sa
    factors = {"momentum": 1.0, "rs": 1.0, "st_rev_5d": 0.0, "near_52w": 0.0,
               "volume": 0.0, "smart_money": 0.0, "quality": 0.0,
               "fama_french": 0.0, "mtf": 0.0, "bb_revert": 0.0, "orb": 0.0, "nr7": 0.0}
    assert sa.group_score(factors, "mid_momentum") == 1.0
```

- [ ] **Step 2: 실패 확인** → import error FAIL

- [ ] **Step 3: 구현** — `score_ablation.py` 생성:

```python
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
            "v2":     {t: r.get("score") for t, r in rows.items()},
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
```

주의: `_nw_tstat`/`_block_bootstrap_ci`의 실제 시그니처를 구현 시 `regime_ic.py:168,187`에서 확인하고 반환 형태(스칼라/튜플)에 맞춰 조정할 것.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_ablation.py -v` → PASS
- [ ] **Step 5: Commit**

```bash
git add score_ablation.py tests/test_ablation.py
git commit -m "feat(ablation): v2/legacy/팩터군 forward IC 비교 CLI — 4주 누적 후 판독"
```

---

### Task 11: D-1 종가베팅 leading signal — market-aware 개편

**Files:**
- Modify: `web_app/macro.py` (`_YF_MAP` :79-93, `_RANGES` :37-54, `_leading_signal` :253-315, `_build` :318-366)
- Test: `tests/test_macro_leading.py` (신규)

**Interfaces:**
- Produces: `_leading_signal(yf_data: dict, market: str) -> dict` — 반환에 `market`, `as_of` 추가. `_build()` payload에 `leading_kr`/`leading_us` 두 판정 + `leading`(KR 기본, 하위호환). Task 12가 소비.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_macro_leading.py` 생성:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))
import macro


def _yf(sp_fut=-1.2, usdkrw=1.2, kospi=-2.1, vix=25.0, vix3m=22.0,
        hyg=-1.5, lqd=0.0, skew=160.0, sp500=-0.5, us10y=0.0):
    return {
        "sp_fut": {"value": 5000.0, "change_pct": sp_fut},
        "usdkrw": {"value": 1450.0, "change_pct": usdkrw},
        "kospi":  {"value": 2500.0, "change_pct": kospi},
        "vix":    {"value": vix, "change_pct": 0.0},
        "vix3m":  {"value": vix3m, "change_pct": 0.0},
        "hyg":    {"value": 75.0, "change_pct": hyg},
        "lqd":    {"value": 105.0, "change_pct": lqd},
        "skew":   {"value": skew, "change_pct": 0.0},
        "sp500":  {"value": 5000.0, "change_pct": sp500},
        "us10y":  {"value": 4.2, "change_pct": us10y},
    }


def test_kr_danger_on_futures_fx_kospi():
    sig = macro._leading_signal(_yf(), market="KR")
    assert sig["market"] == "KR"
    assert sig["safety"] == "danger"          # 선물 -1.2 / 원화 +1.2 / 코스피 -2.1 → 위험
    assert any("선물" in r for r in sig["reasons"])


def test_kr_safe_when_calm():
    sig = macro._leading_signal(
        _yf(sp_fut=0.2, usdkrw=0.1, kospi=0.3, vix=15, vix3m=17, hyg=0.1, lqd=0.0),
        market="KR")
    assert sig["safety"] == "safe"


def test_skew_not_in_judgment():
    """SKEW 극단값이어도 판정에 영향 없어야 (표시 참고값만)."""
    calm = _yf(sp_fut=0.2, usdkrw=0.1, kospi=0.3, vix=15, vix3m=17, hyg=0.1, lqd=0.0)
    sig = macro._leading_signal(dict(calm, skew={"value": 190.0, "change_pct": 0}), market="KR")
    assert sig["safety"] == "safe", "SKEW는 판정에서 제외돼야 함"
    assert sig["skew"] == 190.0


def test_us_mode_uses_intraday_not_krw():
    sig = macro._leading_signal(_yf(sp500=-2.5, usdkrw=9.9), market="US")
    assert sig["market"] == "US"
    assert sig["safety"] in ("caution", "danger")
    assert not any("원" in r or "KRW" in r.upper() for r in sig["reasons"]), "US 모드에 원화 판정 금지"


def test_yf_map_has_futures():
    assert "ES=F" in macro._YF_MAP and "NQ=F" in macro._YF_MAP
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_macro_leading.py -v` → FAIL (market 파라미터 없음 등)

- [ ] **Step 3: 구현** — `web_app/macro.py`:

(1) `_YF_MAP`에 추가: `"ES=F": "sp_fut",` / `"NQ=F": "nq_fut",`
(2) `_RANGES`에 추가: `"sp_fut": (1.0, 100000.0),` / `"nq_fut": (1.0, 100000.0),`
(3) `_ALL_KEYS`(:245-249)에 `"sp_fut", "nq_fut"` 추가.
(4) `_leading_signal`을 다음으로 교체:

```python
def _leading_signal(yf_data: dict, market: str = "KR") -> dict:
    """종가베팅 안전도 — market-aware 판정.

    KR: 미 지수 선물(실시간) + USDKRW(실시간) + KOSPI 당일 + VIX 텀 + HY 스프레드.
    US: 당일 S&P + VIX 텀 + HY 스프레드 + 10Y 급등.
    SKEW는 예측력 근거 부족으로 판정 제외(표시 참고값만).
    danger_count: ≥3 danger / ≥1 caution / 0 safe.
    """
    market = (market or "KR").upper()
    warnings: list[str] = []
    danger_count = 0

    def _chg(key):
        return (yf_data.get(key) or {}).get("change_pct")

    def _val(key):
        return (yf_data.get(key) or {}).get("value")

    # ── 공통: VIX 텀스트럭처 (구조 신호 — 전일 종가여도 유효) ──
    vix_val, vix3m_val = _val("vix"), _val("vix3m")
    vix_term = None
    if vix_val and vix3m_val and vix3m_val > 0:
        vix_term = round(vix_val / vix3m_val, 3)
        if vix_term > 1.05:
            warnings.append(f"VIX 백워데이션 {vix_term:.2f} — 단기 공포 급증 (전일 기준)")
            danger_count += 2
        elif vix_term > 1.0:
            warnings.append(f"VIX 백워데이션 근접 {vix_term:.2f} (전일 기준)")
            danger_count += 1

    # ── 공통: HY 스프레드 프록시 ──
    hyg_chg, lqd_chg = _chg("hyg"), _chg("lqd")
    hy_spread_chg = None
    if hyg_chg is not None and lqd_chg is not None:
        hy_spread_chg = round(hyg_chg - lqd_chg, 2)
        if hy_spread_chg < -1.0:
            warnings.append(f"HY 스프레드 확대 {hy_spread_chg:+.1f}%p — 신용 스트레스 (전일 기준)")
            danger_count += 2
        elif hy_spread_chg < -0.3:
            warnings.append(f"HY 스프레드 소폭 확대 {hy_spread_chg:+.1f}%p (전일 기준)")
            danger_count += 1

    if market == "KR":
        # 미 지수 선물 — 24h 거래라 근실시간. 오늘 밤 미국의 최선 선행 지표
        fut_chg = _chg("sp_fut")
        if fut_chg is not None:
            if fut_chg <= -1.0:
                warnings.append(f"S&P 선물 {fut_chg:+.1f}% — 야간 급락 예고 (실시간)")
                danger_count += 2
            elif fut_chg <= -0.5:
                warnings.append(f"S&P 선물 {fut_chg:+.1f}% 약세 (실시간)")
                danger_count += 1
        krw_chg = _chg("usdkrw")
        if krw_chg is not None:
            if krw_chg >= 1.0:
                warnings.append(f"원/달러 {krw_chg:+.1f}% 급등 — 리스크오프 (실시간)")
                danger_count += 2
            elif krw_chg >= 0.5:
                warnings.append(f"원/달러 {krw_chg:+.1f}% 상승 (실시간)")
                danger_count += 1
        kospi_chg = _chg("kospi")
        if kospi_chg is not None:
            if kospi_chg <= -2.0:
                warnings.append(f"KOSPI 당일 {kospi_chg:+.1f}% 급락")
                danger_count += 2
            elif kospi_chg <= -1.0:
                warnings.append(f"KOSPI 당일 {kospi_chg:+.1f}% 약세")
                danger_count += 1
    else:  # US
        sp_chg = _chg("sp500")
        if sp_chg is not None:
            if sp_chg <= -2.0:
                warnings.append(f"S&P500 당일 {sp_chg:+.1f}% 급락")
                danger_count += 2
            elif sp_chg <= -1.0:
                warnings.append(f"S&P500 당일 {sp_chg:+.1f}% 약세")
                danger_count += 1
        us10y_chg = _chg("us10y")
        if us10y_chg is not None and us10y_chg > _US10Y_STRESS:
            warnings.append(f"10Y 금리 급등 {us10y_chg:+.1f}%")
            danger_count += 1

    safety = "danger" if danger_count >= 3 else ("caution" if danger_count >= 1 else "safe")
    skew_val = _val("skew")
    return {
        "safety": safety,
        "market": market,
        "reasons": warnings,
        "vix_term": vix_term,
        "skew": round(skew_val, 1) if skew_val is not None else None,  # 참고 표시용
        "hy_spread_chg": hy_spread_chg,
        "as_of": datetime.now(_KST).isoformat(timespec="seconds"),
    }
```

(5) `_build()`의 `"leading": _leading_signal(yf_data),` 를 다음으로 교체:

```python
        "leading": _leading_signal(yf_data, "KR"),      # 하위호환 (KR 기본)
        "leading_kr": _leading_signal(yf_data, "KR"),
        "leading_us": _leading_signal(yf_data, "US"),
```

(6) `_build()`의 return을 다음 구조로 변경 — payload를 지역변수로 받아 로그 적재 후 반환:

```python
    _lead_kr = _leading_signal(yf_data, "KR")
    _lead_us = _leading_signal(yf_data, "US")
    payload = {
        "signal": _signal(vix, usdkrw, us10y_chg=us10y_chg, dxy_chg=dxy_chg, vix_prev=vix_prev),
        "leading": _lead_kr,          # 하위호환 (KR 기본)
        "leading_kr": _lead_kr,
        "leading_us": _lead_us,
        "indicators": indicators,
        "ts": datetime.now(_KST).isoformat(timespec="seconds"),
        "stale": False,
    }
    # 판정 히스토리 — 추후 다음날 갭과 대조해 임계 재조정 근거
    try:
        import json as _json
        _log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache_v19")
        os.makedirs(_log_dir, exist_ok=True)
        with open(os.path.join(_log_dir, "leading_signal_log.jsonl"), "a", encoding="utf-8") as _lf:
            _lf.write(_json.dumps(
                {"ts": payload["ts"], "kr": _lead_kr, "us": _lead_us},
                ensure_ascii=False) + "\n")
    except Exception:
        pass
    return payload
```

(파일 상단에 `import os` 추가. (5)항의 dict 내 3줄 교체는 이 구조로 대체된다.)

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_macro_leading.py -v` → 전부 PASS
- [ ] **Step 5: Commit**

```bash
git add web_app/macro.py tests/test_macro_leading.py
git commit -m "feat(macro): 종가베팅 판정 market-aware 개편 — 미 선물·원화·KOSPI 실시간, SKEW 판정 제외"
```

---

### Task 12: D-2 API·프론트 market 전달

**Files:**
- Modify: `web_app/app.py:1572-1586` (`api_macro`), `web_app/static/app.js:5888` (fetch)
- Test: `tests/test_macro_leading.py` (추가)

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def test_api_macro_market_param_wired():
    with open("web_app/app.py", encoding="utf-8") as f:
        src = f.read()
    i = src.index('@app.route("/api/macro")')
    handler = src[i:i + 1200]
    assert "market" in handler, "/api/macro가 market 파라미터를 처리해야"


def test_frontend_passes_market():
    with open("web_app/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "/api/macro?market=" in src
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현**

(1) `app.py`의 `api_macro`:

```python
@app.route("/api/macro")
def api_macro():
    """GET /api/macro?market=KR|US → 상단 신호등 띠용 거시 지표. /api/scan 과 완전 분리."""
    try:
        import macro
        force = request.args.get("force") in ("1", "true", "yes")
        market = (request.args.get("market") or "KR").upper()
        payload = dict(macro.get_macro(force=force))
        lead = payload.get(f"leading_{market.lower()}")
        if lead:
            payload["leading"] = lead
        return jsonify(payload)
    except Exception as e:
        ...  # 기존 except 블록 유지
```

(2) `app.js:5888`:

```javascript
    const res = await fetch(`/api/macro?market=${currentMarket}`);
```

(시장 탭 전환 시 매크로 위젯을 다시 그리는 기존 갱신 주기가 있으므로 추가 트리거는 불요 — 다음 주기부터 반영. 즉시 반영을 원하면 `currentMarket` 변경 핸들러(:476 인근)에서 매크로 refresh 함수를 1회 호출.)

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_macro_leading.py -v` → PASS
- [ ] **Step 5: Commit**

```bash
git add web_app/app.py web_app/static/app.js tests/test_macro_leading.py
git commit -m "feat(macro): /api/macro market 파라미터 + 프론트 현재 탭 전달"
```

---

### Task 13: 통합 확인 + 스펙 대조

- [ ] **Step 1: 전체 테스트** — Run: `python -m pytest tests/ -v` → 전부 PASS (기존 tests/test_nomura_score.py 포함)
- [ ] **Step 2: 구문·임포트 스모크** — Run:

```bash
python -c "import ast; ast.parse(open('quant_nexus_v20.py', encoding='utf-8').read())"
python -c "import sys; sys.path.insert(0,'web_app'); import score_v2, macro, history, engine_adapter"
python -c "import score_ablation"
```

Expected: 무오류.

- [ ] **Step 3: 실데이터 눈검증(선택, 서버 가동 시)** — 스캔 응답에서 v2 TotalScore 분포(균등화)와 `_LegacyScore` 병존 확인, 상단 매크로 띠의 종가베팅 판정에 "실시간/전일 기준" 사유 표기 확인.
- [ ] **Step 4: 푸시** — `git push`
