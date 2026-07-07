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


def test_apply_score_v2_rankpct_decoupled():
    """이원화(2026-07-07): 백분위는 RankPct로 병기, TotalScore/Signal 불변."""
    import os
    os.environ.pop("SCORE_V2", None)
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, mom=float(i * 10), rev=0.0, q=50.0) for i in range(12)]
    apply_score_v2(rows)
    ranks = [r["RankPct"] for r in rows]
    assert ranks == sorted(ranks), "모멘텀 단조증가 → 백분위 단조증가여야"
    assert all(0 <= s <= 100 for s in ranks)
    assert all(r["TotalScore"] == 50.0 for r in rows), "절대 점수는 덮어쓰지 않아야"
    assert all(r["Signal"] == "⏸ NEUTRAL — Hold" for r in rows), "legacy Signal 보존"
    assert rows[0]["_LegacyScore"] == 50.0, "스냅샷 legacy 계열 연속성 유지"


def test_apply_score_v2_small_sample_noop():
    from score_v2 import apply_score_v2
    rows = [_mkrow(i, 10.0, 0.0, 50.0) for i in range(5)]
    apply_score_v2(rows)
    assert all(r["TotalScore"] == 50.0 for r in rows), "표본<10 → 변경 금지"
    assert all("RankPct" not in r for r in rows), "표본<10 → RankPct 미산출"


def test_apply_score_v2_env_off():
    import os
    os.environ["SCORE_V2"] = "0"
    try:
        from score_v2 import apply_score_v2
        rows = [_mkrow(i, float(i * 10), 0.0, 50.0) for i in range(12)]
        apply_score_v2(rows)
        assert all(r["TotalScore"] == 50.0 for r in rows)
        assert all("RankPct" not in r for r in rows)
    finally:
        os.environ.pop("SCORE_V2", None)


def test_snapshot_row_records_v2_series():
    """history 스냅샷: score=절대, legacy=절대, v2=백분위 — IC ablation 재료."""
    # 다른 테스트가 동명의 'history' 모듈을 로드해도 안전하게 파일 경로로 직접 로드
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "web_app", "history.py")
    spec = importlib.util.spec_from_file_location("_webapp_history_for_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _row_for_test = mod._row_for_test
    row = {"TotalScore": 61.4, "_LegacyScore": 61.4, "RankPct": 87.5,
           "_Factors": {"momentum": 70.0}, "EntryStatus": "WAIT"}
    d = _row_for_test(row)
    assert d["score"] == 61.4
    assert d["legacy"] == 61.4
    assert d["v2"] == 87.5


def test_engine_adapter_wires_score_v2():
    with open("web_app/engine_adapter.py", encoding="utf-8") as f:
        src = f.read()
    assert src.count("apply_score_v2(results)") >= 2, "scan_sector/scan_all 양쪽 연결 필요"
