import numpy as np
import pandas as pd
import pytest


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
        show_fib=True, show_sr=True,
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
        show_fib=False, show_sr=False,
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
