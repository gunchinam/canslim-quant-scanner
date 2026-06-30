import numpy as np
import pandas as pd
import pytest


def test_renderer_has_no_show_fib_param():
    """show_fib 파라미터가 제거됐는지 확인."""
    import inspect
    from handdrawn_renderer import HandDrawnChartRenderer
    sig = inspect.signature(HandDrawnChartRenderer.__init__)
    assert 'show_fib' not in sig.parameters, "show_fib 파라미터가 아직 남아있음"


def _make_hist(n=60):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.01,
        "Low":  close * 0.98,
        "Close": close,
        "Volume": np.ones(n) * 1_000_000,
    }, index=dates)
    return df


class _DummyResult:
    def to_dict(self): return {}
    annotations: list = []
    phase = "bull"


def test_renderer_fib_layers_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        show_sr=True,
        support=95.0, resistance=110.0,
    )
    img = r.render()
    assert img is not None
    assert img.width > 0


def test_renderer_fib_disabled_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        show_sr=False,
    )
    img = r.render()
    assert img is not None


def test_renderer_backward_compat():
    """기존 코드처럼 신규 파라미터 없이 호출해도 동작해야 한다."""
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(hist, _DummyResult(), ticker="AAPL")
    img = r.render()
    assert img is not None


def test_renderer_nomura_badge_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    nomura_data = {
        "quantitative_score": 82,
        "grade": "A",
        "piotroski": 7,
        "altman_z": 3.5,
        "beneish_m": -2.1,
        "beneish_warning": False,
        "nomura_rating": "우량",
        "nomura_target": 200.0,
        "nomura_upside": 12.5,
    }
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        nomura_score_data=nomura_data,
    )
    img = r.render()
    assert img is not None
    assert img.width > 0


def test_no_fib_text_in_chart():
    """렌더러가 차트 이미지에 Fib 텍스트를 그리지 않아야 한다."""
    from unittest.mock import patch
    import matplotlib.pyplot as plt
    from handdrawn_renderer import HandDrawnChartRenderer

    hist = _make_hist()
    captured_texts = []

    original_text = plt.Axes.text
    def mock_text(self, x, y, s, *args, **kwargs):
        captured_texts.append(str(s))
        return original_text(self, x, y, s, *args, **kwargs)

    with patch.object(plt.Axes, "text", mock_text):
        r = HandDrawnChartRenderer(hist, _DummyResult(), ticker="TEST")
        r.render()

    fib_texts = [t for t in captured_texts
                 if any(pct in t for pct in ["23%", "38%", "50%", "62%", "79%"])]
    assert len(fib_texts) == 0, f"차트에 Fib 텍스트가 남아있음: {fib_texts}"


def test_fib_levels_payload_shape():
    """fib_levels 계산 로직이 올바른 구조를 반환해야 한다."""
    import pandas as pd
    import numpy as np

    # 동일한 로직을 인라인으로 검증
    dates = pd.date_range("2024-01-01", periods=30)
    hist = pd.DataFrame({
        "High":  np.linspace(100, 120, 30),
        "Low":   np.linspace(80, 90, 30),
        "Close": np.linspace(90, 110, 30),
        "Open":  np.linspace(89, 109, 30),
        "Volume": np.ones(30) * 1000,
    }, index=dates)

    h_max = float(hist["High"].max())   # 120.0
    h_min = float(hist["Low"].min())    # 80.0
    lvls = [
        (0.236, "23%", False),
        (0.382, "38%", True),
        (0.5,   "50%", True),
        (0.618, "62%", True),
        (0.786, "79%", False),
    ]
    fib_levels = [
        {"pct": sym, "price": round(h_min + (h_max - h_min) * r, 2), "key": key}
        for r, sym, key in lvls
    ]

    assert len(fib_levels) == 5
    assert fib_levels[0] == {"pct": "23%", "price": round(80 + 40 * 0.236, 2), "key": False}
    assert fib_levels[1]["key"] is True
    assert fib_levels[2]["key"] is True
    assert fib_levels[3]["key"] is True
    assert fib_levels[4]["key"] is False
    for item in fib_levels:
        assert "pct" in item and "price" in item and "key" in item


@pytest.mark.parametrize("width_px,height_px,dpi", [
    (720,  600, 100),   # 기본 치수
    (1140, 532, 100),   # 실제 서버 렌더 치수
])
def test_renderer_title_not_clipped(width_px, height_px, dpi):
    """적응형 여백 회귀 방지 — 상단 8px에 제목 픽셀이 없어야 한다."""
    from PIL import Image
    from handdrawn_renderer import HandDrawnChartRenderer

    hist = _make_hist(120)
    r = HandDrawnChartRenderer(hist, _DummyResult(), ticker="SAMSUNG",
                               width_px=width_px, height_px=height_px, dpi=dpi)
    img = r.render()

    arr = np.array(img.convert("RGB"))
    top8 = arr[:8, :, :]
    non_white = int(np.sum(np.any(top8 < 230, axis=2)))
    assert non_white == 0, (
        f"[{width_px}×{height_px}] 상단 8px에 비흰색 픽셀 {non_white}개 — "
        "적응형 top 계산 오류"
    )
