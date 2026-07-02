"""Phase A 버그 수정 검증 — 네트워크 없이 코드 구조/함수 단위 검증."""
import re


def _src():
    with open("quant_nexus_v20.py", encoding="utf-8") as f:
        return f.read()


def test_dd_mult_constants_exist():
    src = _src()
    assert '"DD_MULT_EXTREME"' in src
    assert '"DD_MULT_HIGH"' in src


def test_dd_gate_applied_inside_strategy_loop():
    """5전략 루프(all_scores 채우는 for문) 안에 드로다운 감쇄가 있어야 한다."""
    src = _src()
    loop_start = src.index("for _i, _mode in enumerate(_SW_MODES):")
    loop_end = src.index("all_scores[_mode] = round(_f, 1)")
    loop_body = src[loop_start:loop_end]
    assert "_dd_risk" in loop_body, "5전략 루프에 드로다운 게이트 미적용 (composite가 STEP10.6을 덮어씀)"
