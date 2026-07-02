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
