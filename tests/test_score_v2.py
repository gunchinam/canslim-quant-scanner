"""ScoreV2 — 팩터 기록/횡단면 결합 검증 (네트워크 불요)."""


def _src():
    with open("quant_nexus_v20.py", encoding="utf-8") as f:
        return f.read()


def test_factors_and_riskflags_recorded_in_result():
    src = _src()
    assert '"_Factors":' in src, "_analyze_ticker result에 _Factors 부재"
    assert '"RiskFlags":' in src, "_analyze_ticker result에 RiskFlags 부재"
    assert '"st_rev_5d"' in src and '"near_52w"' in src
