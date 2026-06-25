import pytest
from unittest.mock import patch, MagicMock
import tradingkey_api


def test_is_kr_ticker_six_digit():
    assert tradingkey_api.is_kr_ticker("005930") is True

def test_is_kr_ticker_ks_suffix():
    assert tradingkey_api.is_kr_ticker("005930.KS") is True

def test_is_kr_ticker_kq_suffix():
    assert tradingkey_api.is_kr_ticker("035720.KQ") is True

def test_is_kr_ticker_us_stock():
    assert tradingkey_api.is_kr_ticker("AAPL") is False

def test_is_kr_ticker_us_with_numbers():
    assert tradingkey_api.is_kr_ticker("BRK.B") is False

def test_get_tradingkey_data_kr_returns_none():
    result = tradingkey_api.get_tradingkey_data("005930.KS")
    assert result is None

def test_get_score_kr_returns_none():
    result = tradingkey_api.get_score("005930")
    assert result is None

def test_get_support_resistance_kr_returns_none():
    result = tradingkey_api.get_support_resistance("005930.KS")
    assert result is None
