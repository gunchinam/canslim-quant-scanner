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
