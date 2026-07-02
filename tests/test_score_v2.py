"""ScoreV2 — 팩터 기록/횡단면 결합 검증 (네트워크 불요)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))


def _src():
    with open("quant_nexus_v20.py", encoding="utf-8") as f:
        return f.read()


def test_factors_and_riskflags_recorded_in_result():
    src = _src()
    assert '"_Factors":' in src, "_analyze_ticker result에 _Factors 부재"
    assert '"RiskFlags":' in src, "_analyze_ticker result에 RiskFlags 부재"
    assert '"st_rev_5d"' in src and '"near_52w"' in src


def _mkrow(i, mom, rev, q):
    return {"Ticker": f"T{i}", "TotalScore": 50.0, "Signal": "⏸ NEUTRAL — Hold",
            "RiskFlags": [],
            "_Factors": {"momentum": mom, "rs": mom, "st_rev_5d": rev,
                         "near_52w": 0.5, "volume": 50, "smart_money": 50,
                         "quality": q, "fama_french": q,
                         "mtf": 50, "bb_revert": 50, "orb": 0, "nr7": 0}}


def test_apply_score_v2_percentile():
    import os
    os.environ.pop("SCORE_V2", None)
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, mom=float(i * 10), rev=0.0, q=50.0) for i in range(12)]
    apply_score_v2(rows)
    scores = [r["TotalScore"] for r in rows]
    assert scores == sorted(scores), "모멘텀 단조증가 → 점수 단조증가여야"
    assert all(0 <= s <= 100 for s in scores)
    assert rows[0]["_LegacyScore"] == 50.0


def test_apply_score_v2_small_sample_noop():
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, 10.0, 0.0, 50.0) for i in range(5)]
    apply_score_v2(rows)
    assert all(r["TotalScore"] == 50.0 for r in rows), "표본<10 → 변경 금지"


def test_apply_score_v2_riskflag_signal_cap():
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, float(i * 10), 0.0, 50.0) for i in range(12)]
    rows[-1]["RiskFlags"] = ["MDD_EXTREME"]
    apply_score_v2(rows)
    assert "⏸" in rows[-1]["Signal"] or "📉" in rows[-1]["Signal"], "MDD_EXTREME → HOLD 이하로 강등"


def test_apply_score_v2_env_off():
    import os
    os.environ["SCORE_V2"] = "0"
    try:
        from score_v2 import apply_score_v2
        rows = [_mkrow(i, float(i * 10), 0.0, 50.0) for i in range(12)]
        apply_score_v2(rows)
        assert all(r["TotalScore"] == 50.0 for r in rows)
    finally:
        os.environ.pop("SCORE_V2", None)


def test_engine_adapter_wires_score_v2():
    with open("web_app/engine_adapter.py", encoding="utf-8") as f:
        src = f.read()
    assert src.count("apply_score_v2(results)") >= 2, "scan_sector/scan_all 양쪽 연결 필요"
