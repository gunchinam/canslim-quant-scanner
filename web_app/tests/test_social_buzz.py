# web_app/tests/test_social_buzz.py
import importlib
import sys
import types
import unittest
from unittest.mock import patch, MagicMock


def _fresh_module():
    """매 테스트마다 모듈 상태를 초기화해 캐시 오염 방지."""
    if "social_buzz" in sys.modules:
        del sys.modules["social_buzz"]
    import social_buzz
    return social_buzz


class TestParseItem(unittest.TestCase):
    def setUp(self):
        self.sb = _fresh_module()

    def test_standard_keys(self):
        result = self.sb._parse_item({"ticker": "GME", "mentions": 312, "sentiment": 0.72})
        self.assertEqual(result, {"ticker": "GME", "mentions": 312, "sentiment": 0.72})

    def test_alternate_keys(self):
        result = self.sb._parse_item({"symbol": "amc", "no_of_comments": "55", "sentiment_score": "0.5"})
        self.assertEqual(result["ticker"], "AMC")
        self.assertEqual(result["mentions"], 55)
        self.assertAlmostEqual(result["sentiment"], 0.5)

    def test_missing_ticker_returns_none(self):
        self.assertIsNone(self.sb._parse_item({"mentions": 100}))

    def test_invalid_numbers_default_to_zero(self):
        result = self.sb._parse_item({"ticker": "TSLA", "mentions": "bad", "sentiment": None})
        self.assertEqual(result["mentions"], 0)
        self.assertEqual(result["sentiment"], 0.0)


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.sb = _fresh_module()

    def test_passes_high_mentions_positive_sentiment(self):
        items = [{"ticker": "GME", "mentions": 50, "sentiment": 0.5}]
        self.assertEqual(len(self.sb._filter(items)), 1)

    def test_blocks_low_mentions(self):
        items = [{"ticker": "GME", "mentions": 5, "sentiment": 0.5}]
        self.assertEqual(len(self.sb._filter(items)), 0)

    def test_blocks_zero_sentiment(self):
        items = [{"ticker": "GME", "mentions": 50, "sentiment": 0.0}]
        self.assertEqual(len(self.sb._filter(items)), 0)

    def test_blocks_negative_sentiment(self):
        items = [{"ticker": "GME", "mentions": 50, "sentiment": -0.1}]
        self.assertEqual(len(self.sb._filter(items)), 0)


class TestGetCached(unittest.TestCase):
    def setUp(self):
        self.sb = _fresh_module()

    def test_initial_status_is_loading(self):
        snap = self.sb.get_cached()
        self.assertEqual(snap["status"], "loading")
        self.assertEqual(snap["items"], [])

    def test_returns_copy_not_reference(self):
        snap1 = self.sb.get_cached()
        snap2 = self.sb.get_cached()
        self.assertIsNot(snap1, snap2)


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.sb = _fresh_module()

    def test_refresh_updates_cache_on_success(self):
        mock_response = '[{"ticker":"GME","mentions":100,"sentiment":0.8}]'

        class FakeResp:
            def read(self): return mock_response.encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            self.sb.refresh()

        snap = self.sb.get_cached()
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["items"][0]["ticker"], "GME")

    def test_refresh_keeps_old_cache_on_failure(self):
        # Set good cache first
        self.sb._cache["status"] = "ok"
        self.sb._cache["items"] = [{"ticker": "X", "mentions": 99, "sentiment": 0.9}]

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            self.sb.refresh()

        snap = self.sb.get_cached()
        # Status stays "ok" when previous data existed
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(len(snap["items"]), 1)
