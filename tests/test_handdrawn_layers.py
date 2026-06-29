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
