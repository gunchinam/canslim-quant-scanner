# web_app/social_buzz.py
"""social_buzz.py — SwaggyStocks WSB 소셜 버즈 캐시 모듈.

30분 주기 백그라운드 스레드가 SwaggyStocks API를 호출해 언급량·감성 데이터를
캐시한다. API 장애 시 이전 캐시 유지.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

_REFRESH_SEC = int(os.environ.get("SOCIAL_BUZZ_REFRESH_MIN", "30")) * 60
_MENTIONS_MIN = int(os.environ.get("SOCIAL_BUZZ_MENTIONS_MIN", "20"))
_API_URL = os.environ.get(
    "SWAGGY_API_URL",
    "https://api.swaggystocks.com/wsb/sentiment/top",
)
_API_KEY = os.environ.get("SWAGGY_API_KEY", "")
_TIMEOUT = 10

_cache: dict = {"status": "loading", "items": [], "updated_at": None}
_cache_lock = threading.Lock()
_bg_started = False
_bg_lock = threading.Lock()


def _parse_item(raw: dict) -> dict | None:
    """단일 API 응답 항목을 {ticker, mentions, sentiment} 로 정규화."""
    ticker = str(raw.get("ticker") or raw.get("symbol") or "").upper().strip()
    if not ticker:
        return None
    try:
        mentions = int(raw.get("mentions") or raw.get("no_of_comments") or raw.get("count") or 0)
    except (TypeError, ValueError):
        mentions = 0
    try:
        sentiment = float(raw.get("sentiment") or raw.get("sentiment_score") or 0.0)
    except (TypeError, ValueError):
        sentiment = 0.0
    return {"ticker": ticker, "mentions": mentions, "sentiment": round(sentiment, 4)}


def _filter(items: list[dict]) -> list[dict]:
    """언급량 ≥ MENTIONS_MIN AND 감성 > 0 필터."""
    return [i for i in items if i["mentions"] >= _MENTIONS_MIN and i["sentiment"] > 0]


def _fetch_raw() -> list[dict]:
    """SwaggyStocks API 호출 → 정규화된 항목 리스트."""
    req = urllib.request.Request(_API_URL)
    req.add_header("Accept", "application/json")
    if _API_KEY:
        req.add_header("X-API-KEY", _API_KEY)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = (
            data.get("data") or data.get("items") or data.get("tickers") or []
        )
    else:
        raw_items = []
    return [p for item in raw_items if (p := _parse_item(item))]


def refresh() -> None:
    """API 호출 → 필터 → 캐시 갱신. 실패 시 이전 캐시 유지."""
    global _cache
    try:
        raw = _fetch_raw()
        filtered = _filter(raw)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with _cache_lock:
            _cache = {"status": "ok", "items": filtered, "updated_at": now_iso}
        logging.info("[social_buzz] refreshed: %d items", len(filtered))
    except Exception as exc:
        logging.warning("[social_buzz] refresh failed: %s", exc)
        with _cache_lock:
            if _cache["status"] != "ok":
                _cache["status"] = "error"


def get_cached() -> dict:
    """캐시 스냅샷 반환 (thread-safe, 복사본)."""
    with _cache_lock:
        return dict(_cache)


def _bg_loop() -> None:
    refresh()
    while True:
        time.sleep(_REFRESH_SEC)
        refresh()


def init() -> None:
    """백그라운드 갱신 스레드 시작 (멱등 — 중복 호출 안전)."""
    global _bg_started
    with _bg_lock:
        if _bg_started:
            return
        _bg_started = True
    threading.Thread(target=_bg_loop, name="social-buzz-bg", daemon=True).start()
    logging.info("[social_buzz] started (interval=%ds)", _REFRESH_SEC)
