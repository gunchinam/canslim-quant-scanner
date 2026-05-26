# -*- coding: utf-8 -*-
"""swot.py — 종목별 SWOT 정성 분석 생성기 (LLM + 디스크 캐시).

moat.py와 동일한 패턴:
- ANTHROPIC_API_KEY 또는 OPENAI_API_KEY + SWOT_ENABLE_LLM=1 일 때만 활성
- 결과를 cache_v19/swot/{ticker}.json (TTL 90일) 에 저장
- 인메모리 LRU + 디스크 캐시 + 락
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Optional

_log = logging.getLogger(__name__)

# ── 캐시 ─────────────────────────────────────────────────────────────
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache_v19", "swot")
_CACHE_TTL = int(os.environ.get("SWOT_CACHE_TTL", str(90 * 86400)))  # 90일
_cache_lock = threading.Lock()
_mem_cache: dict[str, dict] = {}


def _ensure_dir() -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
    except OSError as e:
        _log.warning("swot cache dir create failed: %s", e)


def _cache_path(ticker: str) -> str:
    safe = ticker.replace("/", "_").replace("\\", "_").replace(":", "_")
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _cache_read(ticker: str) -> Optional[dict]:
    if ticker in _mem_cache:
        return _mem_cache[ticker]
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return None
    try:
        st = os.stat(path)
        if (time.time() - st.st_mtime) > _CACHE_TTL:
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _mem_cache[ticker] = data
        return data
    except (OSError, json.JSONDecodeError) as e:
        _log.debug("swot cache read failed %s: %s", ticker, e)
        return None


def _cache_write(ticker: str, data: dict) -> None:
    _ensure_dir()
    path = _cache_path(ticker)
    try:
        with _cache_lock, open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        _mem_cache[ticker] = data
    except OSError as e:
        _log.debug("swot cache write failed %s: %s", ticker, e)


# ── LLM init (opt-in via SWOT_ENABLE_LLM=1) ──────────────────────────
_LLM_AVAILABLE: Optional[bool] = None
_LLM_PROVIDER: Optional[str] = None
_LLM_CLIENT = None


def _init_llm() -> bool:
    global _LLM_AVAILABLE, _LLM_PROVIDER, _LLM_CLIENT
    if _LLM_AVAILABLE is not None:
        return _LLM_AVAILABLE
    if not os.environ.get("SWOT_ENABLE_LLM"):
        _LLM_AVAILABLE = False
        return False
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            _LLM_CLIENT = anthropic.Anthropic()
            _LLM_PROVIDER = "anthropic"
            _LLM_AVAILABLE = True
            _log.info("swot LLM enabled: anthropic")
            return True
        except Exception as e:
            _log.warning("swot anthropic init failed: %s", e)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai
            _LLM_CLIENT = openai.OpenAI()
            _LLM_PROVIDER = "openai"
            _LLM_AVAILABLE = True
            _log.info("swot LLM enabled: openai")
            return True
        except Exception as e:
            _log.warning("swot openai init failed: %s", e)
    if os.environ.get("GEMINI_API_KEY"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            _LLM_CLIENT = genai.GenerativeModel(
                os.environ.get("SWOT_LLM_MODEL", "gemini-2.0-flash-exp"),
                generation_config={"response_mime_type": "application/json"},
            )
            _LLM_PROVIDER = "gemini"
            _LLM_AVAILABLE = True
            _log.info("swot LLM enabled: gemini")
            return True
        except Exception as e:
            _log.warning("swot gemini init failed: %s", e)
    _LLM_AVAILABLE = False
    return False


_LLM_PROMPT = """다음 종목의 SWOT 분석을 한국어로 작성하라.

티커: {ticker}
종목명: {name}
섹터: {sector}
산업: {industry}
시가총액: {mcap_str}
경제적 해자: {moat}

회사 고유의 사업 모델·제품·고객·경쟁환경·규제·지정학 등 정성적 관점에서 작성.
각 항목은 한 문장(30자 이내), 회사 이름이 떠오를 만큼 구체적이어야 함.
공통적인 표현(예: "성장 여력 있음", "경쟁 심화") 금지.

응답 형식 (JSON 한 줄만, 다른 설명 금지):
{{"S":["...","...","..."],"W":["...","...","..."],"O":["...","...","..."],"T":["...","...","..."]}}

각 분면 3개씩.
예시 (AAPL):
S: "iPhone 생태계 락인 강력", "Services 마진 70%+", "글로벌 브랜드 충성도"
W: "중국 매출 비중 17%", "신제품 카테고리 부진(Vision Pro)"
O: "인도 시장 확대", "온디바이스 AI(Apple Intelligence)"
T: "EU·미국 반독점 규제 강화", "화웨이·샤오미 프리미엄 추격"
"""


def _llm_generate(ticker: str, name: str, sector: str, industry: str,
                  mcap: Optional[float], moat: str) -> Optional[dict]:
    if not _init_llm():
        return None
    if mcap and mcap >= 1e12:
        mcap_str = f"${mcap/1e12:.2f}T"
    elif mcap and mcap >= 1e9:
        mcap_str = f"${mcap/1e9:.1f}B"
    elif mcap:
        mcap_str = f"${mcap/1e6:.0f}M"
    else:
        mcap_str = "불명"
    prompt = _LLM_PROMPT.format(
        ticker=ticker,
        name=name or ticker,
        sector=sector or "불명",
        industry=industry or "불명",
        mcap_str=mcap_str,
        moat=moat or "정보 없음",
    )
    try:
        if _LLM_PROVIDER == "anthropic":
            resp = _LLM_CLIENT.messages.create(
                model=os.environ.get("SWOT_LLM_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
        elif _LLM_PROVIDER == "gemini":
            resp = _LLM_CLIENT.generate_content(prompt)
            raw = (resp.text or "").strip()
        else:
            resp = _LLM_CLIENT.chat.completions.create(
                model=os.environ.get("SWOT_LLM_MODEL", "gpt-4o-mini"),
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
        out = {}
        for k in ("S", "W", "O", "T"):
            arr = data.get(k) or []
            if not isinstance(arr, list):
                arr = []
            out[k] = [str(x).strip()[:80] for x in arr if str(x).strip()][:4]
        if not any(out.values()):
            return None
        return {
            "S": out["S"], "W": out["W"], "O": out["O"], "T": out["T"],
            "source": f"llm:{_LLM_PROVIDER}",
            "generated_at": int(time.time()),
        }
    except Exception as e:
        _log.debug("swot LLM call failed %s: %s", ticker, e)
        return None


def get_swot(ticker: str, name: str = "", sector: str = "",
             industry: str = "", mcap: Optional[float] = None,
             moat: str = "") -> Optional[dict]:
    """캐시 hit → 즉시 반환. miss + LLM 가능 → 생성/저장 후 반환. 실패 → None."""
    cached = _cache_read(ticker)
    if cached:
        return cached
    gen = _llm_generate(ticker, name, sector, industry, mcap, moat)
    if gen:
        _cache_write(ticker, gen)
        return gen
    return None
