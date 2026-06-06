"""Tests for bottleneck_screen — 공급망 병목(scarce-layer) 키워드 근접도 스크리너.

'초벌 패스' 프록시: 사업설명·섹터를 희소층 키워드와 매칭해 병목 근접도(0~100)와
매칭 레이어를 산출. 증거기반 심층판단이 아니라 후보 발굴용.
검증 포인트:
- 상류 희소층(장비·소재·후공정·HBM)은 고점
- 다운스트림/스토리(플랫폼·완성품)는 저점
- 한/영 키워드 모두 매칭
- 무매칭 0, 범위 [0,100]
"""
from __future__ import annotations

import os
import sys
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bottleneck_screen import (  # noqa: E402
    SCARCE_LAYERS,
    SCORECARD_FACTORS,
    SCORECARD_PENALTIES,
    bottleneck_proximity,
    build_bottleneck_brief,
)


class TestTaxonomy(unittest.TestCase):
    def test_layers_have_weight_and_keywords(self):
        self.assertTrue(SCARCE_LAYERS)
        for name, spec in SCARCE_LAYERS.items():
            self.assertIn("weight", spec)
            self.assertIn("keywords", spec)
            self.assertGreaterEqual(spec["weight"], 1)
            self.assertLessEqual(spec["weight"], 5)
            self.assertTrue(spec["keywords"])


class TestProximity(unittest.TestCase):
    def test_equipment_material_scores_high(self):
        r = bottleneck_proximity("반도체 식각 장비 및 CMP 슬러리 소재 제조", sector="반도체")
        self.assertGreaterEqual(r["score"], 60)
        self.assertTrue(r["layers"])

    def test_hbm_packaging_scores_high(self):
        r = bottleneck_proximity("HBM 고대역폭메모리 advanced packaging 후공정", sector="반도체")
        self.assertGreaterEqual(r["score"], 60)

    def test_english_keywords_match(self):
        r = bottleneck_proximity("silicon photonics and CPO optical interconnect supplier")
        self.assertGreaterEqual(r["score"], 50)
        self.assertTrue(r["layers"])

    def test_story_or_downstream_scores_low(self):
        r = bottleneck_proximity("AI 플랫폼 서비스 및 광고 매출 중심 인터넷 기업", sector="인터넷")
        self.assertLess(r["score"], 40)

    def test_no_match_is_zero(self):
        r = bottleneck_proximity("일반 소비재 유통 및 식음료 프랜차이즈", sector="유통")
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["layers"], [])

    def test_score_bounded(self):
        r = bottleneck_proximity(
            "HBM 후공정 advanced packaging CMP 식각 etch 포토레지스트 소재 장비 substrate CPO 전력반도체",
            sector="반도체",
        )
        self.assertGreaterEqual(r["score"], 0)
        self.assertLessEqual(r["score"], 100)

    def test_top_layer_reported(self):
        r = bottleneck_proximity("반도체 검사 장비 테스트 핸들러", sector="반도체")
        self.assertIn("top_layer", r)
        self.assertIsNotNone(r["top_layer"])

    def test_empty_text_safe(self):
        r = bottleneck_proximity("", sector="")
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["layers"], [])


class TestBrief(unittest.TestCase):
    """종목별 심층 브리프 — 외부 병목 스킬 스코어카드와 호환되는 prefilled 출력."""

    def _result(self):
        return {
            "Ticker": "000660.KS", "Name": "SK하이닉스", "Sector": "반도체",
            "Desc": "HBM 고대역폭메모리 advanced packaging 후공정",
            "_PER": 12.3, "_PBR": 3.4, "_ROE": 0.61,
            "BottleneckScore": 90,
            "BottleneckLayers": ["메모리/HBM·인터커넥트", "후공정/어드밴스드 패키징"],
            "BottleneckTop": "메모리/HBM·인터커넥트",
        }

    def test_skeleton_has_all_factor_and_penalty_keys(self):
        brief = build_bottleneck_brief(self._result())
        sk = brief["scorecard_skeleton"]
        for k in SCORECARD_FACTORS:
            self.assertIn(k, sk["factors"])
        for k in SCORECARD_PENALTIES:
            self.assertIn(k, sk["penalties"])
        # 팩터는 리서치로 채울 값이라 0으로 시작
        self.assertTrue(all(v == 0 for v in sk["factors"].values()))

    def test_skeleton_identifies_company_and_market(self):
        brief = build_bottleneck_brief(self._result())
        sk = brief["scorecard_skeleton"]
        self.assertEqual(sk["ticker"], "000660.KS")
        self.assertEqual(sk["company"], "SK하이닉스")
        self.assertIn("Korea", sk["market"])  # .KS → 한국

    def test_research_prompt_contains_context(self):
        brief = build_bottleneck_brief(self._result())
        p = brief["research_prompt"]
        self.assertIn("000660.KS", p)
        self.assertIn("반도체", p)
        # 감지된 희소층이 프롬프트에 시드되어야
        self.assertIn("HBM", p)

    def test_us_ticker_market(self):
        brief = build_bottleneck_brief({"Ticker": "NVDA", "Name": "NVIDIA", "Sector": "Semis"})
        self.assertIn("US", brief["scorecard_skeleton"]["market"])

    def test_missing_fields_safe(self):
        brief = build_bottleneck_brief({"Ticker": "X"})
        self.assertEqual(brief["scorecard_skeleton"]["ticker"], "X")
        self.assertIsInstance(brief["research_prompt"], str)
        self.assertTrue(brief["research_prompt"])


if __name__ == "__main__":
    unittest.main()
