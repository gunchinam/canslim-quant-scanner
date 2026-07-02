"""Phase A 버그 수정 검증 — 네트워크 없이 코드 구조/함수 단위 검증."""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))


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


def test_moat_bonus_idempotent():
    """MoatBonus가 여러 경로에서 호출되어도 1회만 가산되어야 한다."""
    from app import _apply_moat_bonus
    rows = [{"Ticker": "T", "TotalScore": 70.0, "MoatBonus": 5}]
    _apply_moat_bonus(rows)
    assert rows[0]["TotalScore"] == 75.0
    _apply_moat_bonus(rows)  # 2회째 — 누적되면 안 됨
    assert rows[0]["TotalScore"] == 75.0, "MoatBonus 이중 가산"


def test_midcap_alpha_no_moat_double_count():
    """midcap_alpha promo에서 moat이 이중 반영되면 안 된다."""
    from engine_adapter import _attach_midcap_alpha
    base = {"Indices": ["SP400"], "TotalScore": 70, "RSRating": 80,
            "_MarketCap": 9e9, "_VolRatio": 1.0, "_EPS": 1.0}
    r_moat = dict(base, MoatBonus=3)
    r_plain = dict(base, MoatBonus=0)
    _attach_midcap_alpha([r_moat])
    _attach_midcap_alpha([r_plain])
    # moat 기여는 ts를 통해서만 — promo 직접 가산이 없어야 동일
    assert r_moat["MidcapPromotion"] == r_plain["MidcapPromotion"], "moat 이중 반영"
