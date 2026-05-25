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


def test_f1_size_band_pass():
    f = mb.Fundamentals(market_cap=1_000_000_000)
    assert mb.eval_f1(f, mb.DEFAULTS) is True

def test_f1_size_too_small():
    f = mb.Fundamentals(market_cap=100_000_000)
    assert mb.eval_f1(f, mb.DEFAULTS) is False

def test_f1_size_too_large():
    f = mb.Fundamentals(market_cap=5_000_000_000)
    assert mb.eval_f1(f, mb.DEFAULTS) is False

def test_f1_missing():
    f = mb.Fundamentals(market_cap=None)
    assert mb.eval_f1(f, mb.DEFAULTS) is None

def test_f2_profitability():
    assert mb.eval_f2(mb.Fundamentals(ebitda=1.0, fcf=1.0), mb.DEFAULTS) is True
    assert mb.eval_f2(mb.Fundamentals(ebitda=-1.0, fcf=1.0), mb.DEFAULTS) is False
    assert mb.eval_f2(mb.Fundamentals(ebitda=1.0, fcf=None), mb.DEFAULTS) is None

def test_f8_entry():
    ok = mb.Fundamentals(from_52w_high=-0.20, return_1m=0.10)
    assert mb.eval_f8(ok, mb.DEFAULTS) is True
    too_high = mb.Fundamentals(from_52w_high=-0.05, return_1m=0.10)
    assert mb.eval_f8(too_high, mb.DEFAULTS) is False
    too_deep = mb.Fundamentals(from_52w_high=-0.60, return_1m=0.10)
    assert mb.eval_f8(too_deep, mb.DEFAULTS) is False
    overheated = mb.Fundamentals(from_52w_high=-0.20, return_1m=0.40)
    assert mb.eval_f8(overheated, mb.DEFAULTS) is False
