"""FIB-DCA-001: _renderFibDcaPlan — 현재가보다 위 레벨을 매수 후보로 잡던 버그 회귀 테스트.

이전 로직은 fibLevels 중 가격이 가장 높은 3개를 무조건 골랐기 때문에,
현재가가 이미 하락해 그 레벨들 밑으로 내려간 경우에도 상위 가격을
분할매수 목표로 제시했다. app.js 의 _renderFibDcaPlan 함수를 node 로
직접 evaluate 해서 검증한다.
"""

from __future__ import annotations

import json
import re
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


def _run_render(fib_levels, current_price) -> dict:
    fmt_price_src = _extract_function_src("fmtPrice")
    render_src = _extract_function_src("_renderFibDcaPlan")
    script = f"""
    let capturedHtml = null;
    const _elMock = {{ style: {{}} }};
    Object.defineProperty(_elMock, 'innerHTML', {{
      set(v) {{ capturedHtml = v; }},
      get() {{ return capturedHtml; }},
    }});
    const document = {{ getElementById: (id) => (id === 'dp-split-plan' ? _elMock : null) }};
    const _lastDetailData = {{ Price: {json.dumps(current_price)} }};

    {fmt_price_src}
    {render_src}

    _renderFibDcaPlan({json.dumps(fib_levels)});
    process.stdout.write(Buffer.from(JSON.stringify({{ html: capturedHtml }}), 'utf8'));
    """
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("node not available")
    res = subprocess.run([node_exe, "-e", script], capture_output=True, check=True)
    return json.loads(res.stdout.decode("utf-8"))


def _extract_row_prices(html: str) -> list[float]:
    if not html:
        return []
    return [float(p.replace(",", "")) for p in re.findall(r'class="spl-price">([\d,.]+)<', html)]


def test_deep_pullback_only_uses_levels_below_current_price():
    """현재가(95)가 이미 fib 23/38/50%(120/110/100) 아래로 내려간 상황.

    수정 전에는 항상 가격이 가장 높은 3개(120/110/100)를 골라
    전부 현재가보다 위인 매수 목표를 보여줬다.
    """
    fib_levels = [
        {"pct": "23%", "price": 120, "key": False},
        {"pct": "38%", "price": 110, "key": True},
        {"pct": "50%", "price": 100, "key": True},
        {"pct": "62%", "price": 90, "key": True},
        {"pct": "79%", "price": 80, "key": False},
    ]
    out = _run_render(fib_levels, current_price=95)
    prices = _extract_row_prices(out["html"])
    assert prices, "분할매수 플랜이 렌더링되어야 한다"
    assert all(p < 95 for p in prices), f"현재가보다 낮은 레벨만 나와야 하는데: {prices}"
    assert prices == [90.0, 80.0]


def test_normal_case_still_picks_top_three_below_price():
    """현재가(150)가 모든 fib 레벨보다 위인 정상적인 경우 — 상위 3개(120/110/100) 그대로."""
    fib_levels = [
        {"pct": "23%", "price": 120, "key": False},
        {"pct": "38%", "price": 110, "key": True},
        {"pct": "50%", "price": 100, "key": True},
        {"pct": "62%", "price": 90, "key": True},
        {"pct": "79%", "price": 80, "key": False},
    ]
    out = _run_render(fib_levels, current_price=150)
    prices = _extract_row_prices(out["html"])
    assert prices == [120.0, 110.0, 100.0]


def test_only_one_level_below_price_hides_panel():
    """유효 레벨이 1개뿐이면 (< 2 가드) 패널을 렌더링하지 않는다."""
    fib_levels = [
        {"pct": "23%", "price": 120, "key": False},
        {"pct": "38%", "price": 110, "key": True},
        {"pct": "50%", "price": 100, "key": True},
        {"pct": "62%", "price": 90, "key": True},
        {"pct": "79%", "price": 80, "key": False},
    ]
    out = _run_render(fib_levels, current_price=85)
    assert out["html"] is None
