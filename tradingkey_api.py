import re
import time
import logging
from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 4 * 3600

_session = cffi_requests.Session(impersonate="chrome120")

_KR_PATTERN = re.compile(r"^\d{6}(\.KS|\.KQ)?$", re.IGNORECASE)


def is_kr_ticker(ticker: str) -> bool:
    return bool(_KR_PATTERN.match(ticker.strip()))


def get_tradingkey_data(ticker: str) -> dict | None:
    if is_kr_ticker(ticker):
        return None
    cached = _cache.get(ticker)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    return None  # 실제 API 호출은 Task 2에서 구현


def get_score(ticker: str) -> dict | None:
    if is_kr_ticker(ticker):
        return None
    data = get_tradingkey_data(ticker)
    if data is None:
        return None
    return data.get("score")


def get_support_resistance(ticker: str) -> tuple[float, float] | None:
    if is_kr_ticker(ticker):
        return None
    data = get_tradingkey_data(ticker)
    if data is None:
        return None
    rt = data.get("risk_technical", {})
    s = rt.get("support")
    r = rt.get("resistance")
    if s and r:
        return (float(s), float(r))
    return None
