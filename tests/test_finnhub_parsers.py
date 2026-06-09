"""finnhub_api 순수 파서 단위테스트 — 네트워크 호출 없음."""
from __future__ import annotations

import os
import sys
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from finnhub_api import _parse_profile2  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
