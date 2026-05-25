import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import multibagger as mb


def test_defaults_present():
    assert mb.DEFAULTS["F1_MCAP_MIN"] == 200_000_000
    assert mb.DEFAULTS["F1_MCAP_MAX"] == 2_000_000_000


def test_fundamentals_all_optional():
    f = mb.Fundamentals()
    assert f.market_cap is None
