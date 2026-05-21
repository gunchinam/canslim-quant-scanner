"""Tests for deeptech story correction gate."""
import pytest
from quant_nexus_v20 import _is_deeptech_story


def _row(sector="드론·우주", rev_growth=0.10, market_cap=200_000_000_000):
    return {
        "Sector": sector,
        "_RevenueGrowth": rev_growth,
        "_MarketCap": market_cap,
    }


def test_deeptech_story_pass_with_growing_revenue_and_large_cap():
    assert _is_deeptech_story("099320.KQ", _row()) is True


def test_deeptech_story_fail_when_sector_not_in_whitelist():
    assert _is_deeptech_story("005930.KS", _row(sector="반도체")) is False


def test_deeptech_story_fail_when_revenue_not_growing():
    assert _is_deeptech_story("099320.KQ", _row(rev_growth=-0.05)) is False


def test_deeptech_story_fail_when_revenue_flat():
    assert _is_deeptech_story("099320.KQ", _row(rev_growth=0.0)) is False


def test_deeptech_story_fail_when_market_cap_too_small():
    assert _is_deeptech_story("X.KQ", _row(market_cap=50_000_000_000)) is False


def test_deeptech_story_fail_on_missing_sector():
    row = _row()
    row["Sector"] = ""
    assert _is_deeptech_story("X", row) is False


def test_deeptech_story_fail_on_missing_revenue_growth():
    row = _row()
    row.pop("_RevenueGrowth", None)
    assert _is_deeptech_story("X", row) is False


def test_deeptech_story_fail_on_missing_market_cap():
    row = _row()
    row.pop("_MarketCap", None)
    assert _is_deeptech_story("X", row) is False
