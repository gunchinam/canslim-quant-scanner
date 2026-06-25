# TradingKey + 노무라式 Plan 1: 데이터 파운데이션

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tradingkey_api.py`와 `nomura_score.py`를 구현하여 TradingKey 데이터 수집 및 노무라式 스코어링 엔진을 완성한다.

**Architecture:** curl_cffi로 TradingKey 내부 JSON API를 호출하고 4시간 메모리 캐시에 저장한다. nomura_score.py는 수집된 데이터와 yfinance 재무 데이터를 조합해 Piotroski F-Score, Altman Z-Score, Beneish M-Score, 100점 정량 스코어를 산출하고 노무라式 레이팅을 반환한다.

**Tech Stack:** Python 3.11+, curl_cffi, yfinance, numpy

## Global Constraints

- 미국 종목 전용: KR 종목(6자리 숫자, `.KS`/`.KQ` 접미사)은 `None` 반환
- 캐시 TTL: 4시간 (`4 * 3600`)
- 캐시 패턴: `finnhub_api.py`와 동일한 `dict[str, tuple[dict, float]]`
- curl_cffi impersonate: `"chrome120"`
- 파일 위치: 프로젝트 루트 (`C:\Users\Administrator\Documents\카카오톡 받은 파일\종목스캐너\`)
- 테스트 위치: `tests/` 디렉토리
- 브랜딩: "노무라式" (노무라 X)
- 실패 시 `None` 반환, 예외 로그만 출력 — 앱 크래시 금지

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `tradingkey_api.py` (신규) | TradingKey API 호출 + 파싱 + 캐시 |
| `nomura_score.py` (신규) | 노무라式 정량 스코어링 엔진 |
| `tests/test_tradingkey_api.py` (신규) | tradingkey_api 단위 테스트 |
| `tests/test_nomura_score.py` (신규) | nomura_score 단위 테스트 |

---

## Task 1: tradingkey_api.py — 스켈레톤 + KR 가드

**Files:**
- Create: `tradingkey_api.py`
- Create: `tests/test_tradingkey_api.py`

**Interfaces:**
- Produces:
  - `is_kr_ticker(ticker: str) -> bool`
  - `get_tradingkey_data(ticker: str) -> dict | None`
  - `get_score(ticker: str) -> dict | None`
  - `get_support_resistance(ticker: str) -> tuple[float, float] | None`

- [ ] **Step 1: tests/ 디렉토리 확인**

```bash
ls tests/ 2>/dev/null || mkdir tests && touch tests/__init__.py
```

- [ ] **Step 2: KR 가드 실패 테스트 작성**

`tests/test_tradingkey_api.py` 생성:
```python
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
```

- [ ] **Step 3: 실패 확인**

```bash
cd "C:\Users\Administrator\Documents\카카오톡 받은 파일\종목스캐너"
.venv64\Scripts\python -m pytest tests/test_tradingkey_api.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'tradingkey_api'`

- [ ] **Step 4: tradingkey_api.py 스켈레톤 작성**

`tradingkey_api.py` 생성:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_tradingkey_api.py -v
```
Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add tradingkey_api.py tests/test_tradingkey_api.py tests/__init__.py
git commit -m "feat(tradingkey): 스켈레톤 + KR 가드 구현"
```

---

## Task 2: tradingkey_api.py — API 엔드포인트 발굴 및 호출 구현

> ⚠️ **사전 작업 필요:** 브라우저 DevTools로 TradingKey API 엔드포인트를 먼저 발굴해야 한다.
>
> 1. Chrome에서 `https://www.tradingkey.com/stock/AAPL` 접속
> 2. DevTools → Network → Fetch/XHR 탭
> 3. `score`, `institutional`, `analyst` 등 키워드로 JSON 응답 찾기
> 4. Request URL, Headers(특히 `Authorization`, `x-api-key` 등) 기록
> 5. 아래 `_TK_BASE_URL`과 `_fetch_raw` 함수에 실제 값 채우기

**Files:**
- Modify: `tradingkey_api.py`
- Modify: `tests/test_tradingkey_api.py`

**Interfaces:**
- Consumes: `is_kr_ticker()`, `_session` (Task 1)
- Produces: `get_tradingkey_data(ticker)` — 실제 API 응답 반환

- [ ] **Step 1: API 구조 파악 후 mock 테스트 추가**

`tests/test_tradingkey_api.py`에 추가:
```python
MOCK_TK_RESPONSE = {
    "score": {
        "overall": 72, "valuation": 65, "growth": 78,
        "profitability": 80, "momentum": 70, "risk": 60,
        "industry_rank": 284, "industry_total": 488,
        "overall_rank": 169, "overall_total": 4571,
        "sector_percentile": 41.8,
    },
    "institutional": {
        "confidence_score": 0.72, "holding_pct": 62.3,
        "holding_qoq": -7.1, "top_holder": "Vanguard",
        "top_holder_pct": 8.2, "top_holder_chg": -0.3,
    },
    "analyst": {
        "consensus": "Buy", "target_price": 315.0,
        "upside_pct": 7.5, "analyst_count": 42,
        "buy_count": 28, "hold_count": 12, "sell_count": 2,
    },
    "valuation": {
        "pe_ttm": 29.5, "pe_dynamic": 27.1, "pe_static": 31.2,
        "pb": 8.4, "eps_ttm": 6.58, "market_cap": 2800000000000.0,
    },
    "fundamentals": {
        "roe": 0.147, "roa": 0.223, "gross_margin": 0.456,
        "net_profit": 0.253, "dividend_yield": 0.005, "payout_ratio": 0.15,
    },
    "risk_technical": {
        "beta": 1.21, "risk_rate": 3.2, "reward_risk": 2.1,
        "support": 278.0, "resistance": 351.0,
        "volume_ratio": 1.3, "amplitude": 2.8, "turnover_ratio": 0.7,
    },
    "performance": {
        "1d": 0.8, "5d": 2.1, "1m": 5.3,
        "6m": 12.4, "ytd": 18.7, "1y": 24.1,
    },
}


@patch("tradingkey_api._fetch_raw")
def test_get_tradingkey_data_us_stock(mock_fetch):
    tradingkey_api._cache.clear()
    mock_fetch.return_value = MOCK_TK_RESPONSE
    result = tradingkey_api.get_tradingkey_data("AAPL")
    assert result is not None
    assert result["score"]["overall"] == 72
    assert result["_source"] == "tradingkey"
    assert "_cached_at" in result


@patch("tradingkey_api._fetch_raw")
def test_get_tradingkey_data_cache_hit(mock_fetch):
    tradingkey_api._cache.clear()
    mock_fetch.return_value = MOCK_TK_RESPONSE
    tradingkey_api.get_tradingkey_data("AAPL")
    tradingkey_api.get_tradingkey_data("AAPL")
    assert mock_fetch.call_count == 1  # 두 번째는 캐시


@patch("tradingkey_api._fetch_raw")
def test_get_support_resistance(mock_fetch):
    tradingkey_api._cache.clear()
    mock_fetch.return_value = MOCK_TK_RESPONSE
    result = tradingkey_api.get_support_resistance("AAPL")
    assert result == (278.0, 351.0)


@patch("tradingkey_api._fetch_raw")
def test_get_tradingkey_data_api_failure_returns_none(mock_fetch):
    tradingkey_api._cache.clear()
    mock_fetch.side_effect = Exception("network error")
    result = tradingkey_api.get_tradingkey_data("AAPL")
    assert result is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_tradingkey_api.py::test_get_tradingkey_data_us_stock -v
```
Expected: FAIL (`_fetch_raw` not defined)

- [ ] **Step 3: `_fetch_raw` + `get_tradingkey_data` 구현**

`tradingkey_api.py`에서 `get_tradingkey_data` 함수를 교체:
```python
# DevTools에서 발굴한 실제 엔드포인트로 교체 필요
_TK_BASE_URL = "https://api.tradingkey.com/v1"  # ← 실제 URL로 교체

_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tradingkey.com/",
    # DevTools에서 발견한 인증 헤더 추가
}


def _fetch_raw(ticker: str) -> dict:
    """TradingKey API 실제 호출. DevTools에서 발굴한 엔드포인트 사용."""
    # 실제 엔드포인트 구조에 따라 아래를 수정
    url = f"{_TK_BASE_URL}/stock/{ticker}/overview"
    resp = _session.get(url, headers=_DEFAULT_HEADERS, timeout=10)
    resp.raise_for_status()
    raw = resp.json()
    # API 응답 구조에 맞게 파싱 (DevTools 응답 참고)
    return _parse_response(raw)


def _parse_response(raw: dict) -> dict:
    """TradingKey API 응답을 표준 스키마로 변환."""
    # DevTools 응답 구조에 맞게 각 섹션 파싱
    # 예시: raw["data"]["scoreInfo"] → score 섹션
    return {
        "score": _parse_score(raw),
        "institutional": _parse_institutional(raw),
        "analyst": _parse_analyst(raw),
        "valuation": _parse_valuation(raw),
        "fundamentals": _parse_fundamentals(raw),
        "risk_technical": _parse_risk_technical(raw),
        "performance": _parse_performance(raw),
    }


def _parse_score(raw: dict) -> dict:
    # DevTools 응답 구조에 맞게 구현
    s = raw.get("score", raw.get("scoreInfo", {}))
    return {
        "overall": int(s.get("overall", 0)),
        "valuation": int(s.get("valuation", 0)),
        "growth": int(s.get("growth", 0)),
        "profitability": int(s.get("profitability", 0)),
        "momentum": int(s.get("momentum", 0)),
        "risk": int(s.get("risk", 0)),
        "industry_rank": int(s.get("industry_rank", 0)),
        "industry_total": int(s.get("industry_total", 0)),
        "overall_rank": int(s.get("overall_rank", 0)),
        "overall_total": int(s.get("overall_total", 0)),
        "sector_percentile": float(s.get("sector_percentile", 0)),
    }


def _parse_institutional(raw: dict) -> dict:
    i = raw.get("institutional", raw.get("institutionInfo", {}))
    return {
        "confidence_score": float(i.get("confidence_score", 0)),
        "holding_pct": float(i.get("holding_pct", 0)),
        "holding_qoq": float(i.get("holding_qoq", 0)),
        "top_holder": str(i.get("top_holder", "")),
        "top_holder_pct": float(i.get("top_holder_pct", 0)),
        "top_holder_chg": float(i.get("top_holder_chg", 0)),
    }


def _parse_analyst(raw: dict) -> dict:
    a = raw.get("analyst", raw.get("analystInfo", {}))
    return {
        "consensus": str(a.get("consensus", "Hold")),
        "target_price": float(a.get("target_price", 0)),
        "upside_pct": float(a.get("upside_pct", 0)),
        "analyst_count": int(a.get("analyst_count", 0)),
        "buy_count": int(a.get("buy_count", 0)),
        "hold_count": int(a.get("hold_count", 0)),
        "sell_count": int(a.get("sell_count", 0)),
    }


def _parse_valuation(raw: dict) -> dict:
    v = raw.get("valuation", raw.get("valuationInfo", {}))
    return {
        "pe_ttm": float(v.get("pe_ttm", 0)),
        "pe_dynamic": float(v.get("pe_dynamic", 0)),
        "pe_static": float(v.get("pe_static", 0)),
        "pb": float(v.get("pb", 0)),
        "eps_ttm": float(v.get("eps_ttm", 0)),
        "market_cap": float(v.get("market_cap", 0)),
    }


def _parse_fundamentals(raw: dict) -> dict:
    f = raw.get("fundamentals", raw.get("fundamentalInfo", {}))
    return {
        "roe": float(f.get("roe", 0)),
        "roa": float(f.get("roa", 0)),
        "gross_margin": float(f.get("gross_margin", 0)),
        "net_profit": float(f.get("net_profit", 0)),
        "dividend_yield": float(f.get("dividend_yield", 0)),
        "payout_ratio": float(f.get("payout_ratio", 0)),
    }


def _parse_risk_technical(raw: dict) -> dict:
    r = raw.get("risk_technical", raw.get("riskInfo", {}))
    return {
        "beta": float(r.get("beta", 1.0)),
        "risk_rate": float(r.get("risk_rate", 0)),
        "reward_risk": float(r.get("reward_risk", 0)),
        "support": float(r.get("support", 0)),
        "resistance": float(r.get("resistance", 0)),
        "volume_ratio": float(r.get("volume_ratio", 1.0)),
        "amplitude": float(r.get("amplitude", 0)),
        "turnover_ratio": float(r.get("turnover_ratio", 0)),
    }


def _parse_performance(raw: dict) -> dict:
    p = raw.get("performance", raw.get("performanceInfo", {}))
    return {
        "1d": float(p.get("1d", 0)),
        "5d": float(p.get("5d", 0)),
        "1m": float(p.get("1m", 0)),
        "6m": float(p.get("6m", 0)),
        "ytd": float(p.get("ytd", 0)),
        "1y": float(p.get("1y", 0)),
    }


def get_tradingkey_data(ticker: str) -> dict | None:
    if is_kr_ticker(ticker):
        return None
    cached = _cache.get(ticker)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    try:
        raw = _fetch_raw(ticker)
        data = {**raw, "_cached_at": time.time(), "_source": "tradingkey"}
        _cache[ticker] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TradingKey fetch failed for {ticker}: {e}")
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_tradingkey_api.py -v
```
Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add tradingkey_api.py tests/test_tradingkey_api.py
git commit -m "feat(tradingkey): API 호출 + 파싱 + 캐시 구현"
```

---

## Task 3: nomura_score.py — Piotroski F-Score

**Files:**
- Create: `nomura_score.py`
- Create: `tests/test_nomura_score.py`

**Interfaces:**
- Consumes: `yfinance` (이미 설치됨)
- Produces: `calculate_piotroski(ticker: str) -> int`  — 0~9

- [ ] **Step 1: Piotroski 테스트 작성**

`tests/test_nomura_score.py` 생성:
```python
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import nomura_score


# --- Piotroski ---

def _make_financials(net_income, total_assets, operating_cf,
                     long_term_debt, current_assets, current_liabilities,
                     shares, revenue, gross_profit,
                     prev_net_income=None, prev_total_assets=None,
                     prev_long_term_debt=None, prev_current_assets=None,
                     prev_current_liabilities=None, prev_shares=None,
                     prev_revenue=None, prev_gross_profit=None):
    """yfinance balance_sheet / income_stmt / cashflow 구조 모킹 헬퍼."""
    # 현재 연도
    curr = {
        "Net Income": net_income,
        "Total Assets": total_assets,
        "Operating Cash Flow": operating_cf,
        "Long Term Debt": long_term_debt,
        "Current Assets": current_assets,
        "Current Liabilities": current_liabilities,
        "Ordinary Shares Number": shares,
        "Total Revenue": revenue,
        "Gross Profit": gross_profit,
    }
    # 이전 연도 (기본값: 동일)
    prev = {
        "Net Income": prev_net_income or net_income,
        "Total Assets": prev_total_assets or total_assets,
        "Long Term Debt": prev_long_term_debt or long_term_debt,
        "Current Assets": prev_current_assets or current_assets,
        "Current Liabilities": prev_current_liabilities or current_liabilities,
        "Ordinary Shares Number": prev_shares or shares,
        "Total Revenue": prev_revenue or revenue,
        "Gross Profit": prev_gross_profit or gross_profit,
    }
    return curr, prev


def test_piotroski_perfect_score():
    """9/9 조건 충족 케이스."""
    curr, prev = _make_financials(
        net_income=1000, total_assets=5000, operating_cf=1200,
        long_term_debt=500, current_assets=2000, current_liabilities=800,
        shares=100, revenue=10000, gross_profit=4000,
        prev_net_income=800, prev_total_assets=4500,
        prev_long_term_debt=600, prev_current_assets=1500,
        prev_current_liabilities=700, prev_shares=105,
        prev_revenue=9000, prev_gross_profit=3400,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        score = nomura_score.calculate_piotroski("AAPL")
    assert score == 9


def test_piotroski_zero_score():
    """0/9 조건: 손실, 음수 CF, 부채증가 등."""
    curr, prev = _make_financials(
        net_income=-500, total_assets=5000, operating_cf=-200,
        long_term_debt=1000, current_assets=800, current_liabilities=900,
        shares=110, revenue=8000, gross_profit=2000,
        prev_net_income=800, prev_total_assets=4000,
        prev_long_term_debt=800, prev_current_assets=1500,
        prev_current_liabilities=700, prev_shares=100,
        prev_revenue=9000, prev_gross_profit=3200,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        score = nomura_score.calculate_piotroski("AAPL")
    assert score == 0


def test_piotroski_returns_int():
    curr, prev = _make_financials(
        net_income=100, total_assets=1000, operating_cf=150,
        long_term_debt=200, current_assets=500, current_liabilities=300,
        shares=50, revenue=2000, gross_profit=800,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        result = nomura_score.calculate_piotroski("AAPL")
    assert isinstance(result, int)
    assert 0 <= result <= 9


def test_piotroski_kr_returns_none():
    result = nomura_score.calculate_piotroski("005930.KS")
    assert result is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py::test_piotroski_returns_int -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: nomura_score.py 구현 (Piotroski 부분)**

`nomura_score.py` 생성:
```python
import logging
import yfinance as yf
from tradingkey_api import is_kr_ticker

logger = logging.getLogger(__name__)


def _get_financials(ticker: str) -> tuple[dict, dict]:
    """yfinance에서 현재/이전 연도 재무 데이터 반환."""
    t = yf.Ticker(ticker)
    bs = t.balance_sheet
    inc = t.income_stmt
    cf = t.cashflow

    def _get(df, key, col=0, default=0.0):
        try:
            return float(df.loc[key].iloc[col])
        except Exception:
            return float(default)

    curr = {
        "Net Income": _get(inc, "Net Income"),
        "Total Assets": _get(bs, "Total Assets"),
        "Operating Cash Flow": _get(cf, "Operating Cash Flow"),
        "Long Term Debt": _get(bs, "Long Term Debt"),
        "Current Assets": _get(bs, "Current Assets"),
        "Current Liabilities": _get(bs, "Current Liabilities"),
        "Ordinary Shares Number": _get(bs, "Ordinary Shares Number"),
        "Total Revenue": _get(inc, "Total Revenue"),
        "Gross Profit": _get(inc, "Gross Profit"),
    }
    prev = {
        "Net Income": _get(inc, "Net Income", col=1),
        "Total Assets": _get(bs, "Total Assets", col=1),
        "Long Term Debt": _get(bs, "Long Term Debt", col=1),
        "Current Assets": _get(bs, "Current Assets", col=1),
        "Current Liabilities": _get(bs, "Current Liabilities", col=1),
        "Ordinary Shares Number": _get(bs, "Ordinary Shares Number", col=1),
        "Total Revenue": _get(inc, "Total Revenue", col=1),
        "Gross Profit": _get(inc, "Gross Profit", col=1),
    }
    return curr, prev


def calculate_piotroski(ticker: str) -> int | None:
    """Piotroski F-Score (0~9) 계산."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, prev = _get_financials(ticker)
        score = 0

        ta = curr["Total Assets"]
        prev_ta = prev["Total Assets"]
        if ta == 0:
            return 0

        # F1: ROA > 0
        roa = curr["Net Income"] / ta
        if roa > 0:
            score += 1

        # F2: Operating Cash Flow > 0
        if curr["Operating Cash Flow"] > 0:
            score += 1

        # F3: ROA 증가
        prev_roa = prev["Net Income"] / prev_ta if prev_ta else 0
        if roa > prev_roa:
            score += 1

        # F4: Accruals (CF/TA > ROA)
        if curr["Operating Cash Flow"] / ta > roa:
            score += 1

        # F5: 부채 비율 감소
        curr_lev = curr["Long Term Debt"] / ta
        prev_lev = prev["Long Term Debt"] / prev_ta if prev_ta else 0
        if curr_lev < prev_lev:
            score += 1

        # F6: 유동비율 증가
        curr_cr = curr["Current Assets"] / curr["Current Liabilities"] if curr["Current Liabilities"] else 0
        prev_cr = prev["Current Assets"] / prev["Current Liabilities"] if prev["Current Liabilities"] else 0
        if curr_cr > prev_cr:
            score += 1

        # F7: 신주 발행 없음 (주식수 감소 또는 동일)
        if curr["Ordinary Shares Number"] <= prev["Ordinary Shares Number"]:
            score += 1

        # F8: Gross Margin 개선
        curr_gm = curr["Gross Profit"] / curr["Total Revenue"] if curr["Total Revenue"] else 0
        prev_gm = prev["Gross Profit"] / prev["Total Revenue"] if prev["Total Revenue"] else 0
        if curr_gm > prev_gm:
            score += 1

        # F9: Asset Turnover 증가
        curr_at = curr["Total Revenue"] / ta
        prev_at = prev["Total Revenue"] / prev_ta if prev_ta else 0
        if curr_at > prev_at:
            score += 1

        return score
    except Exception as e:
        logger.warning(f"Piotroski calculation failed for {ticker}: {e}")
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py -v
```
Expected: 4개 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add nomura_score.py tests/test_nomura_score.py
git commit -m "feat(nomura): Piotroski F-Score 구현"
```

---

## Task 4: nomura_score.py — Altman Z-Score + Beneish M-Score

**Files:**
- Modify: `nomura_score.py`
- Modify: `tests/test_nomura_score.py`

**Interfaces:**
- Consumes: `_get_financials()` (Task 3)
- Produces:
  - `calculate_altman_z(ticker: str) -> float | None`
  - `calculate_beneish_m(ticker: str) -> tuple[float, bool] | None`

- [ ] **Step 1: Altman Z + Beneish 테스트 추가**

`tests/test_nomura_score.py`에 추가:
```python
def test_altman_z_safe_zone():
    """Z > 2.99 = 안전."""
    curr, prev = _make_financials(
        net_income=2000, total_assets=10000, operating_cf=2500,
        long_term_debt=1000, current_assets=4000, current_liabilities=2000,
        shares=100, revenue=15000, gross_profit=7000,
    )
    # 시가총액과 EBIT는 별도로 필요
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_market_cap", return_value=25000.0), \
         patch("nomura_score._get_ebit", return_value=2500.0), \
         patch("nomura_score._get_retained_earnings", return_value=5000.0):
        z = nomura_score.calculate_altman_z("AAPL")
    assert z is not None
    assert z > 2.99


def test_altman_z_returns_float():
    curr, prev = _make_financials(
        net_income=100, total_assets=1000, operating_cf=150,
        long_term_debt=200, current_assets=500, current_liabilities=300,
        shares=50, revenue=2000, gross_profit=800,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_market_cap", return_value=2000.0), \
         patch("nomura_score._get_ebit", return_value=200.0), \
         patch("nomura_score._get_retained_earnings", return_value=300.0):
        z = nomura_score.calculate_altman_z("AAPL")
    assert isinstance(z, float)


def test_beneish_no_warning():
    """M < -1.78: 분식 없음."""
    curr, prev = _make_financials(
        net_income=1000, total_assets=5000, operating_cf=1200,
        long_term_debt=500, current_assets=2000, current_liabilities=800,
        shares=100, revenue=10000, gross_profit=4500,
        prev_net_income=900, prev_total_assets=4800,
        prev_revenue=9500, prev_gross_profit=4200,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_ppe", return_value=(1000.0, 950.0)), \
         patch("nomura_score._get_depreciation", return_value=200.0), \
         patch("nomura_score._get_long_term_assets", return_value=(500.0, 480.0)), \
         patch("nomura_score._get_sga", return_value=(500.0, 480.0)):
        m, warning = nomura_score.calculate_beneish_m("AAPL")
    assert isinstance(m, float)
    assert warning is False


def test_beneish_kr_returns_none():
    result = nomura_score.calculate_beneish_m("005930.KS")
    assert result is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py::test_altman_z_returns_float -v
```
Expected: FAIL (`calculate_altman_z` not defined)

- [ ] **Step 3: Altman Z + Beneish M 구현**

`nomura_score.py`에 추가:
```python
def _get_market_cap(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).info.get("marketCap", 0))
    except Exception:
        return 0.0


def _get_ebit(ticker: str) -> float:
    try:
        t = yf.Ticker(ticker)
        ebit = t.income_stmt.loc["EBIT"].iloc[0]
        return float(ebit)
    except Exception:
        try:
            inc = t.income_stmt
            op_income = float(inc.loc["Operating Income"].iloc[0])
            return op_income
        except Exception:
            return 0.0


def _get_retained_earnings(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).balance_sheet.loc["Retained Earnings"].iloc[0])
    except Exception:
        return 0.0


def _get_ppe(ticker: str) -> tuple[float, float]:
    try:
        bs = yf.Ticker(ticker).balance_sheet
        curr = float(bs.loc["Net PPE"].iloc[0])
        prev = float(bs.loc["Net PPE"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def _get_depreciation(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).cashflow.loc["Depreciation And Amortization"].iloc[0])
    except Exception:
        return 0.0


def _get_long_term_assets(ticker: str) -> tuple[float, float]:
    try:
        bs = yf.Ticker(ticker).balance_sheet
        curr = float(bs.loc["Other Non Current Assets"].iloc[0])
        prev = float(bs.loc["Other Non Current Assets"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def _get_sga(ticker: str) -> tuple[float, float]:
    try:
        inc = yf.Ticker(ticker).income_stmt
        curr = float(inc.loc["Selling General And Administration"].iloc[0])
        prev = float(inc.loc["Selling General And Administration"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def calculate_altman_z(ticker: str) -> float | None:
    """Altman Z-Score. >2.99=안전, 1.81~2.99=회색, <1.81=위험."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, _ = _get_financials(ticker)
        ta = curr["Total Assets"]
        if ta == 0:
            return None

        working_capital = curr["Current Assets"] - curr["Current Liabilities"]
        retained_earnings = _get_retained_earnings(ticker)
        ebit = _get_ebit(ticker)
        market_cap = _get_market_cap(ticker)
        total_liabilities = curr["Long Term Debt"] + curr["Current Liabilities"]
        revenue = curr["Total Revenue"]

        x1 = working_capital / ta
        x2 = retained_earnings / ta
        x3 = ebit / ta
        x4 = market_cap / total_liabilities if total_liabilities else 0
        x5 = revenue / ta

        z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        return round(float(z), 3)
    except Exception as e:
        logger.warning(f"Altman Z failed for {ticker}: {e}")
        return None


def calculate_beneish_m(ticker: str) -> tuple[float, bool] | None:
    """Beneish M-Score. > -1.78: 분식 의심 경고."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, prev = _get_financials(ticker)
        ta_curr = curr["Total Assets"]
        ta_prev = prev["Total Assets"]
        if ta_curr == 0 or ta_prev == 0:
            return None

        rev_curr = curr["Total Revenue"]
        rev_prev = prev["Total Revenue"]
        gp_curr = curr["Gross Profit"]
        gp_prev = prev["Gross Profit"]
        ppe_curr, ppe_prev = _get_ppe(ticker)
        depr = _get_depreciation(ticker)
        lt_curr, lt_prev = _get_long_term_assets(ticker)
        sga_curr, sga_prev = _get_sga(ticker)

        # DSRI: Days Sales Receivable Index
        rec_curr = curr["Current Assets"] * 0.3  # 근사값
        rec_prev = prev["Current Assets"] * 0.3
        dsri = (rec_curr / rev_curr) / (rec_prev / rev_prev) if rev_prev and rev_curr else 1

        # GMI: Gross Margin Index
        gm_prev = gp_prev / rev_prev if rev_prev else 0
        gm_curr = gp_curr / rev_curr if rev_curr else 0
        gmi = gm_prev / gm_curr if gm_curr else 1

        # AQI: Asset Quality Index
        aqi_curr = (ta_curr - curr["Current Assets"] - ppe_curr) / ta_curr
        aqi_prev = (ta_prev - prev["Current Assets"] - ppe_prev) / ta_prev
        aqi = aqi_curr / aqi_prev if aqi_prev else 1

        # SGI: Sales Growth Index
        sgi = rev_curr / rev_prev if rev_prev else 1

        # DEPI: Depreciation Index
        dep_rate_prev = ppe_prev / (ppe_prev + depr) if (ppe_prev + depr) else 0.5
        dep_rate_curr = ppe_curr / (ppe_curr + depr) if (ppe_curr + depr) else 0.5
        depi = dep_rate_prev / dep_rate_curr if dep_rate_curr else 1

        # SGAI: SGA Expense Index
        sgai = (sga_curr / rev_curr) / (sga_prev / rev_prev) if sga_prev and rev_prev and rev_curr else 1

        # LVGI: Leverage Index
        lev_curr = curr["Long Term Debt"] / ta_curr
        lev_prev = prev["Long Term Debt"] / ta_prev
        lvgi = lev_curr / lev_prev if lev_prev else 1

        # TATA: Total Accruals to Total Assets
        tata = (curr["Net Income"] - curr["Operating Cash Flow"]) / ta_curr

        m = (-4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi
             + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi)

        return round(float(m), 3), m > -1.78
    except Exception as e:
        logger.warning(f"Beneish M failed for {ticker}: {e}")
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py -v
```
Expected: 8개 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add nomura_score.py tests/test_nomura_score.py
git commit -m "feat(nomura): Altman Z-Score + Beneish M-Score 구현"
```

---

## Task 5: nomura_score.py — 100점 정량 스코어 + 최종 레이팅

**Files:**
- Modify: `nomura_score.py`
- Modify: `tests/test_nomura_score.py`

**Interfaces:**
- Consumes: `calculate_piotroski()`, `get_tradingkey_data()` (Task 1~4)
- Produces: `get_nomura_score(ticker: str) -> dict | None`

- [ ] **Step 1: 최종 스코어 테스트 추가**

`tests/test_nomura_score.py`에 추가:
```python
from tests.test_tradingkey_api import MOCK_TK_RESPONSE


@patch("nomura_score.calculate_piotroski", return_value=7)
@patch("nomura_score.calculate_altman_z", return_value=3.5)
@patch("nomura_score.calculate_beneish_m", return_value=(-2.1, False))
@patch("nomura_score.get_tradingkey_data", return_value=MOCK_TK_RESPONSE)
def test_get_nomura_score_structure(mock_tk, mock_ben, mock_alt, mock_pio):
    result = nomura_score.get_nomura_score("AAPL")
    assert result is not None
    assert "quantitative_score" in result
    assert "grade" in result
    assert "piotroski" in result
    assert "altman_z" in result
    assert "beneish_m" in result
    assert "beneish_warning" in result
    assert "nomura_rating" in result
    assert "nomura_target" in result
    assert "nomura_upside" in result


@patch("nomura_score.calculate_piotroski", return_value=9)
@patch("nomura_score.calculate_altman_z", return_value=4.0)
@patch("nomura_score.calculate_beneish_m", return_value=(-2.5, False))
@patch("nomura_score.get_tradingkey_data", return_value={**MOCK_TK_RESPONSE,
    "score": {**MOCK_TK_RESPONSE["score"], "overall": 95}})
def test_get_nomura_score_conviction_buy(mock_tk, mock_ben, mock_alt, mock_pio):
    result = nomura_score.get_nomura_score("NVDA")
    assert result["grade"] == "A+"
    assert result["nomura_rating"] == "Conviction Buy"


@patch("nomura_score.calculate_piotroski", return_value=7)
@patch("nomura_score.calculate_altman_z", return_value=3.5)
@patch("nomura_score.calculate_beneish_m", return_value=(-2.1, False))
@patch("nomura_score.get_tradingkey_data", return_value=MOCK_TK_RESPONSE)
def test_get_nomura_score_range(mock_tk, mock_ben, mock_alt, mock_pio):
    result = nomura_score.get_nomura_score("AAPL")
    assert 0 <= result["quantitative_score"] <= 100


def test_get_nomura_score_kr_returns_none():
    result = nomura_score.get_nomura_score("005930.KS")
    assert result is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py::test_get_nomura_score_structure -v
```
Expected: FAIL

- [ ] **Step 3: 100점 스코어 + 레이팅 로직 구현**

`nomura_score.py`에 추가:
```python
from tradingkey_api import get_tradingkey_data as _get_tk_data


def _calc_quantitative_score(tk_data: dict, piotroski: int) -> int:
    """100점 정량 스코어 계산."""
    score = 0

    inst = tk_data.get("institutional", {})
    fund = tk_data.get("fundamentals", {})
    val = tk_data.get("valuation", {})
    perf = tk_data.get("performance", {})
    tk_score = tk_data.get("score", {})

    # QoQ 모멘텀 (20점)
    holding_qoq = inst.get("holding_qoq", 0)
    if holding_qoq > 5:
        score += 8
    elif holding_qoq > 0:
        score += 5
    elif holding_qoq > -5:
        score += 2

    rev_1m = perf.get("1m", 0)
    if rev_1m > 5:
        score += 7
    elif rev_1m > 0:
        score += 4
    elif rev_1m > -5:
        score += 1

    piotroski_qoq = min(5, piotroski // 2) if piotroski else 0
    score += piotroski_qoq

    # YoY 성장성 (20점)
    growth = tk_score.get("growth", 0)
    score += int(growth / 100 * 20)

    # 밸류에이션 (30점)
    val_score = tk_score.get("valuation", 0)
    score += int(val_score / 100 * 30)

    # 수익성 (30점)
    prof_score = tk_score.get("profitability", 0)
    roe = fund.get("roe", 0)
    gross_margin = fund.get("gross_margin", 0)

    prof_pts = int(prof_score / 100 * 20)
    roe_pts = min(5, int(roe * 100 / 5)) if roe > 0 else 0
    gm_pts = min(5, int(gross_margin * 100 / 10)) if gross_margin > 0 else 0
    score += prof_pts + roe_pts + gm_pts

    return min(100, max(0, score))


def _score_to_grade(score: int) -> str:
    if score >= 90: return "A+"
    if score >= 75: return "A"
    if score >= 55: return "B"
    if score >= 35: return "C"
    return "D"


def _grade_to_rating(grade: str) -> str:
    mapping = {"A+": "Conviction Buy", "A": "Buy", "B": "Neutral", "C": "Reduce", "D": "Sell"}
    return mapping.get(grade, "Neutral")


def get_nomura_score(ticker: str) -> dict | None:
    """노무라式 종합 스코어 반환."""
    if is_kr_ticker(ticker):
        return None
    try:
        tk_data = _get_tk_data(ticker)
        if tk_data is None:
            return None

        piotroski = calculate_piotroski(ticker) or 0
        altman_z = calculate_altman_z(ticker)
        beneish_result = calculate_beneish_m(ticker)
        beneish_m = beneish_result[0] if beneish_result else None
        beneish_warning = beneish_result[1] if beneish_result else False

        q_score = _calc_quantitative_score(tk_data, piotroski)
        grade = _score_to_grade(q_score)
        rating = _grade_to_rating(grade)

        analyst = tk_data.get("analyst", {})
        target = analyst.get("target_price", 0.0)
        upside = analyst.get("upside_pct", 0.0)

        return {
            "quantitative_score": q_score,
            "grade": grade,
            "piotroski": piotroski,
            "altman_z": altman_z,
            "beneish_m": beneish_m,
            "beneish_warning": beneish_warning,
            "nomura_rating": rating,
            "nomura_target": float(target),
            "nomura_upside": float(upside),
        }
    except Exception as e:
        logger.warning(f"get_nomura_score failed for {ticker}: {e}")
        return None
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_nomura_score.py -v
```
Expected: 12개 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add nomura_score.py tests/test_nomura_score.py
git commit -m "feat(nomura): 100점 정량 스코어 + 노무라式 레이팅 완성"
```

---

## Task 6: Flask API 엔드포인트 연결

**Files:**
- Modify: `web_app/__init__.py` 또는 라우터 파일 (기존 구조에 따라)
- Modify: `tests/test_api_nomura.py` (신규)

**Interfaces:**
- Consumes: `get_nomura_score()`, `get_tradingkey_data()` (Task 1~5)
- Produces: `GET /api/nomura-score/<ticker>` → JSON

- [ ] **Step 1: 엔드포인트 테스트 작성**

`tests/test_api_nomura.py` 생성:
```python
import pytest
from unittest.mock import patch
# 기존 앱 임포트 방식 확인 후 수정
# from web_app import create_app 또는 from app import app


MOCK_NOMURA = {
    "quantitative_score": 78,
    "grade": "A",
    "piotroski": 7,
    "altman_z": 3.2,
    "beneish_m": -2.1,
    "beneish_warning": False,
    "nomura_rating": "Buy",
    "nomura_target": 315.0,
    "nomura_upside": 7.5,
}

MOCK_TK = {
    "score": {"overall": 72, "sector_percentile": 41.8},
    "analyst": {"consensus": "Buy", "target_price": 315.0, "upside_pct": 7.5},
    "risk_technical": {"support": 278.0, "resistance": 351.0},
}


@patch("nomura_score.get_nomura_score", return_value=MOCK_NOMURA)
@patch("tradingkey_api.get_tradingkey_data", return_value=MOCK_TK)
def test_nomura_score_endpoint(mock_tk, mock_ns, client):
    resp = client.get("/api/nomura-score/AAPL")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["nomura_rating"] == "Buy"
    assert data["quantitative_score"] == 78


@patch("nomura_score.get_nomura_score", return_value=None)
def test_nomura_score_endpoint_kr(mock_ns, client):
    resp = client.get("/api/nomura-score/005930.KS")
    assert resp.status_code == 404
```

- [ ] **Step 2: 기존 Flask 앱 라우터 파일 확인**

```bash
grep -r "def.*route\|@app.route\|@blueprint" web_app/ --include="*.py" -l
```

- [ ] **Step 3: `/api/nomura-score/<ticker>` 엔드포인트 추가**

기존 라우터 파일(확인된 경로)에 추가:
```python
from nomura_score import get_nomura_score
from tradingkey_api import get_tradingkey_data


@app.route("/api/nomura-score/<ticker>")
def api_nomura_score(ticker):
    ns = get_nomura_score(ticker.upper())
    if ns is None:
        return {"error": "US stocks only or data unavailable"}, 404
    tk = get_tradingkey_data(ticker.upper()) or {}
    return {
        **ns,
        "tk_score": tk.get("score", {}),
        "tk_analyst": tk.get("analyst", {}),
        "tk_risk_technical": tk.get("risk_technical", {}),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv64\Scripts\python -m pytest tests/test_api_nomura.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add web_app/ tests/test_api_nomura.py
git commit -m "feat(api): /api/nomura-score/<ticker> 엔드포인트 추가"
```

---

## 스펙 커버리지 체크

| 스펙 요구사항 | 커버 Task |
|---------------|-----------|
| tradingkey_api.py 신규 | Task 1, 2 |
| KR 종목 가드 | Task 1 |
| 4시간 캐시 | Task 2 |
| curl_cffi chrome120 | Task 2 |
| 7-레이어 데이터 스키마 | Task 2 |
| Piotroski F-Score | Task 3 |
| Altman Z-Score | Task 4 |
| Beneish M-Score | Task 4 |
| 100점 정량 스코어 | Task 5 |
| 노무라式 레이팅 4단계 | Task 5 |
| Flask API 연결 | Task 6 |

> Plan 2 (비주얼 통합)와 Plan 3 (AI 강화)는 이 플랜 완료 후 작성합니다.
