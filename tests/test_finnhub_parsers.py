"""finnhub_api 순수 파서 단위테스트 — 네트워크 호출 없음."""
from __future__ import annotations

import os
import sys
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from finnhub_api import _parse_profile2, _parse_insider_sentiment  # noqa: E402


class TestParseProfile2(unittest.TestCase):
    def test_full_profile(self) -> None:
        raw = {
            "name": "Apple Inc", "ipo": "1980-12-12",
            "shareOutstanding": 15000.0, "finnhubIndustry": "Technology",
            "exchange": "NASDAQ NMS - GLOBAL MARKET",
            "weburl": "https://www.apple.com/", "logo": "https://x/aapl.png",
        }
        out = _parse_profile2(raw)
        self.assertEqual(out["logo"], "https://x/aapl.png")
        self.assertEqual(out["ipo"], "1980-12-12")
        self.assertEqual(out["share_outstanding"], 15000.0)
        self.assertEqual(out["industry"], "Technology")
        self.assertEqual(out["exchange"], "NASDAQ NMS - GLOBAL MARKET")

    def test_empty_input(self) -> None:
        self.assertEqual(_parse_profile2(None), {})
        self.assertEqual(_parse_profile2({}), {})

    def test_partial_fields_only_present_keys(self) -> None:
        out = _parse_profile2({"name": "X", "logo": "https://x/x.png"})
        self.assertEqual(out["logo"], "https://x/x.png")
        self.assertNotIn("ipo", out)


class TestParseInsiderSentiment(unittest.TestCase):
    def test_latest_and_trend(self) -> None:
        raw = {"data": [
            {"year": 2026, "month": 1, "mspr": -10.0, "change": -100},
            {"year": 2026, "month": 2, "mspr": 5.0, "change": 50},
            {"year": 2026, "month": 3, "mspr": 20.0, "change": 200},
        ]}
        out = _parse_insider_sentiment(raw)
        self.assertEqual(out["mspr"], 20.0)
        self.assertEqual(out["mspr_trend"], [-10.0, 5.0, 20.0])
        self.assertEqual(out["mspr_change"], 15.0)

    def test_empty(self) -> None:
        self.assertEqual(_parse_insider_sentiment(None), {})
        self.assertEqual(_parse_insider_sentiment({"data": []}), {})

    def test_single_month_no_change(self) -> None:
        out = _parse_insider_sentiment({"data": [{"year": 2026, "month": 3, "mspr": 7.0}]})
        self.assertEqual(out["mspr"], 7.0)
        self.assertEqual(out["mspr_trend"], [7.0])
        self.assertEqual(out["mspr_change"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
