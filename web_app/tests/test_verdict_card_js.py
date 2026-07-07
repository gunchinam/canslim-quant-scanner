"""VC-001: _composeVerdict(detail, nomura, fourAxis) — 드로어 종합 판정 카드 규칙 검증.

app.js 의 _composeVerdict 함수를 node 로 직접 extract·evaluate 해서 검증한다.
_entryLabel/​_renderFibDcaPlan 테스트와 동일한 패턴(중괄호 매칭으로 함수 블록만 잘라
node -e 로 실행)을 사용한다. _composeVerdict 는 DOM/외부 함수 의존이 없는 순수 함수라
이 블록만 잘라내도 그대로 실행 가능해야 한다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "static" / "app.js"


def _extract_function_src(name: str) -> str:
    src = APP_JS.read_text(encoding="utf-8")
    fn_start = src.index(f"function {name}")
    depth = 0
    i = src.index("{", fn_start)
    while i < len(src):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                fn_end = i + 1
                break
        i += 1
    else:
        raise RuntimeError(f"could not find end of {name} function")
    return src[fn_start:fn_end]


def _run_compose(detail, nomura, four_axis) -> dict:
    fn_src = _extract_function_src("_composeVerdict")
    script = f"""
    {fn_src}
    const out = _composeVerdict({json.dumps(detail)}, {json.dumps(nomura)}, {json.dumps(four_axis)});
    process.stdout.write(Buffer.from(JSON.stringify(out), 'utf8'));
    """
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("node not available")
    res = subprocess.run([node_exe, "-e", script], capture_output=True, check=True)
    return json.loads(res.stdout.decode("utf-8"))


# ① knife → WAIT (급락 진행 중)
def test_knife_timing_yields_wait():
    detail = {"EntryPlan": {"dd_velocity_5d": -6}}
    out = _run_compose(detail, None, None)
    assert out["verdict"] == "WAIT"
    assert "급락" in out["label"]
    assert out["axes"]["timing"] == "knife"
    assert any("급락" in r for r in out["reasons"])
    assert any("낙폭 속도 진정" in t["text"] for t in out["triggers"])


# ② expensive (스크린샷 재현: price 296000 > DCF max 262161) → WAIT
def test_expensive_valuation_yields_wait():
    detail = {"Price": 296000}
    nomura = {
        "football_field": [{"method": "DCF", "min_price": 200000, "max_price": 262161}],
        "current_price": 296000,
    }
    out = _run_compose(detail, nomura, None)
    assert out["verdict"] == "WAIT"
    assert "밸류에이션" in out["label"]
    assert out["axes"]["valuation"] == "expensive"
    assert any("262,161" in r and "초과" in r for r in out["reasons"])
    assert any("262,161" in t["text"] and "밴드 상단" in t["text"] for t in out["triggers"])


# ③ quality red — knife와 동시일 때도 AVOID가 우선
def test_quality_red_overrides_knife_to_avoid():
    detail = {
        "AltmanZ": 1.2,
        "PiotroskiF": 2,
        "EntryPlan": {"dd_velocity_5d": -6},
    }
    out = _run_compose(detail, None, None)
    assert out["verdict"] == "AVOID"
    assert "회피" in out["label"]
    assert out["axes"]["quality"] == "red"
    assert out["axes"]["timing"] == "knife"


# ④ good + cheap + strong → BUY
def test_good_cheap_strong_yields_buy():
    detail = {
        "AltmanZ": 3.5,
        "PiotroskiF": 7,
        "Price": 100,
        "EntryPlan": {"dd_velocity_5d": 0},
    }
    nomura = {
        "piotroski": 7,
        "altman_z": 3.5,
        "quantitative_score": 80,
        "nomura_upside": 20,
        "football_field": [{"method": "DCF", "min_price": 110, "max_price": 130}],
        "current_price": 100,
    }
    four_axis = {"trend": {"score": 5}, "momentum": {"score": 5}, "volume": {"score": 5}}
    out = _run_compose(detail, nomura, four_axis)
    assert out["verdict"] == "BUY"
    assert out["axes"] == {"quality": "good", "valuation": "cheap", "timing": "strong"}
    assert out["confidence"] == "높음"


# ⑤ 평범(모든 축이 중립) → SPLIT
def test_ordinary_signals_yield_split():
    detail = {
        "AltmanZ": 2.5,
        "PiotroskiF": 5,
        "Price": 100,
        "EntryPlan": {"dd_velocity_5d": -1, "mdd_current": -5},
    }
    nomura = {
        "piotroski": 5,
        "altman_z": 2.5,
        "quantitative_score": 60,
        "nomura_upside": 5,
        "football_field": [{"method": "DCF", "min_price": 80, "max_price": 120}],
        "current_price": 100,
    }
    four_axis = {"trend": {"score": 3}, "momentum": {"score": 3}, "volume": {"score": 3}}
    out = _run_compose(detail, nomura, four_axis)
    assert out["verdict"] == "SPLIT"
    assert out["axes"] == {"quality": "mid", "valuation": "fair", "timing": "ok"}
    assert any(t.get("scrollTarget") == "dp-split-plan" for t in out["triggers"])


# ⑥ nomura 결측 → 유효 축 2개, confidence 중간
def test_missing_nomura_leaves_two_valid_axes_mid_confidence():
    detail = {
        "AltmanZ": 2.5,
        "PiotroskiF": 5,
        "EntryPlan": {"dd_velocity_5d": -1},
    }
    four_axis = {"trend": {"score": 3}, "momentum": {"score": 3}, "volume": {"score": 3}}
    out = _run_compose(detail, None, four_axis)
    assert out["axes"]["valuation"] is None
    assert out["axes"]["quality"] is not None
    assert out["axes"]["timing"] is not None
    assert out["confidence"] == "중간"


# ⑦ 전부 결측 → HOLD
def test_all_missing_yields_hold():
    out = _run_compose({}, None, None)
    assert out["verdict"] == "HOLD"
    assert "보류" in out["label"]
    assert out["axes"] == {"quality": None, "valuation": None, "timing": None}
    assert out["confidence"] == "낮음"
    assert out["reasons"] == []
    assert out["triggers"] == []
