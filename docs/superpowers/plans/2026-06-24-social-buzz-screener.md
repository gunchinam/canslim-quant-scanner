# Social Buzz Screener 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SwaggyStocks API로 WSB 언급량·긍정 감성 종목을 필터링하고, TotalScore 내림차순으로 정렬한 상위 5개를 메인 페이지 카드 위젯에 표시한다.

**Architecture:** `social_buzz.py`가 30분 주기 백그라운드 스레드로 SwaggyStocks API를 가져와 필터·캐시한다. `/api/social-buzz` 엔드포인트가 캐시에서 읽은 소셜 데이터에 기존 `_scan_results_cache`의 TotalScore를 병합한 뒤 JSON 반환한다. 프론트엔드는 DOMContentLoaded 시 fetch하여 카드 위젯을 렌더링한다.

**Tech Stack:** Python stdlib(`urllib.request`, `threading`, `json`), Flask `jsonify`, 기존 `app.js`의 `_stockGrade()` · `openDetail()`, 기존 `scanner.css` CSS 변수

## Global Constraints

- 신규 pip 패키지 설치 금지 — stdlib + 기존 의존성만 사용
- 기존 `TotalScore` 계산 로직 변경 금지
- `SWAGGY_API_KEY` 환경변수 없으면 소셜 위젯 숨김 처리 (graceful degradation)
- 모든 캐시 접근은 `threading.Lock()` 보호
- 등급 기준: S≥75, A≥60, B≥45, C<45 (`app.js`의 `_stockGrade` 동일)

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `web_app/social_buzz.py` (신규) | SwaggyStocks fetch + 필터 + 캐시 |
| `web_app/tests/test_social_buzz.py` (신규) | social_buzz 단위 테스트 |
| `web_app/app.py` (수정) | `/api/social-buzz` 라우트 + `social_buzz.init()` 호출 |
| `web_app/templates/scanner.html` (수정) | WSB 위젯 HTML |
| `web_app/static/scanner.css` (수정) | 위젯 CSS |
| `web_app/static/app.js` (수정) | 위젯 fetch·렌더 JS |

---

## Task 1: `social_buzz.py` — 코어 모듈

**Files:**
- Create: `web_app/social_buzz.py`
- Test: `web_app/tests/test_social_buzz.py`

**Interfaces:**
- Produces:
  - `init() -> None` — 백그라운드 스레드 시작 (멱등)
  - `get_cached() -> dict` — `{"status": "loading"|"ok"|"error", "items": [...], "updated_at": str|None}`
  - `refresh() -> None` — 즉시 갱신 (테스트·강제 새로고침용)
  - `items` 원소: `{"ticker": str, "mentions": int, "sentiment": float}`

- [ ] **Step 1: 실패 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd "C:\Users\Administrator\Documents\카카오톡 받은 파일\종목스캐너"
python -m pytest web_app/tests/test_social_buzz.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'social_buzz'`

- [ ] **Step 3: `social_buzz.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
cd "C:\Users\Administrator\Documents\카카오톡 받은 파일\종목스캐너"
python -m pytest web_app/tests/test_social_buzz.py -v
```
Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add web_app/social_buzz.py web_app/tests/test_social_buzz.py
git commit -m "feat(social-buzz): SwaggyStocks 캐시 모듈 + 단위 테스트"
```

---

## Task 2: `/api/social-buzz` 엔드포인트

**Files:**
- Modify: `web_app/app.py` — `/api/social-buzz` 라우트 추가 + `social_buzz.init()` 호출

**Interfaces:**
- Consumes: `social_buzz.get_cached() -> dict`, `_scan_results_cache` (app.py 내부)
- Produces:
  ```json
  {"status": "ok", "updated_at": "ISO8601", "items": [
    {"ticker": "GME", "mentions": 312, "sentiment": 0.72, "total_score": 68.0}
  ]}
  ```

- [ ] **Step 1: `app.py`에 `social_buzz.init()` 호출 추가**

`app.py` 3632번 줄 (`threading.Thread(target=_cold_start_fill, ...)`) 바로 아래에 추가:

```python
# ── 소셜 버즈 백그라운드 갱신 ──
try:
    import social_buzz as _social_buzz
    if os.environ.get("SWAGGY_API_KEY", "").strip():
        _social_buzz.init()
    else:
        logging.info("[social_buzz] SWAGGY_API_KEY 미설정 — 소셜 버즈 비활성화")
except Exception as _e:
    logging.warning("[social_buzz] init 실패: %s", _e)
```

- [ ] **Step 2: `/api/social-buzz` 라우트 추가**

`app.py`의 `@app.route("/api/serenity/<ticker>")` 블록 바로 앞에 추가:

```python
@app.route("/api/social-buzz")
def api_social_buzz():
    """GET /api/social-buzz → WSB 인기 종목 상위 N개 (소셜 버즈 × TotalScore).

    social_buzz 캐시에서 소셜 데이터를 읽고, _scan_results_cache에서
    TotalScore를 병합한 뒤 점수 내림차순 상위 N개를 반환한다.
    SWAGGY_API_KEY 미설정 시 status="disabled" 반환.
    """
    if not os.environ.get("SWAGGY_API_KEY", "").strip():
        return jsonify({"status": "disabled", "items": [], "updated_at": None})
    try:
        import social_buzz as _sb
        snap = _sb.get_cached()
        if snap["status"] != "ok":
            return jsonify({"status": snap["status"], "items": [], "updated_at": snap.get("updated_at")})

        # _scan_results_cache에서 ticker → TotalScore 역인덱스 구성
        ticker_scores: dict[str, float | None] = {}
        with _scan_results_cache_lock:
            for cache_val in _scan_results_cache.values():
                for row in (cache_val.get("data") or []):
                    t = (row.get("Ticker") or "").upper()
                    if t and t not in ticker_scores:
                        ts = row.get("TotalScore")
                        ticker_scores[t] = float(ts) if isinstance(ts, (int, float)) else None

        top_n = int(os.environ.get("SOCIAL_BUZZ_TOP_N", "5"))
        enriched = [
            {**item, "total_score": ticker_scores.get(item["ticker"])}
            for item in snap["items"]
        ]
        enriched.sort(
            key=lambda x: x["total_score"] if x["total_score"] is not None else -1,
            reverse=True,
        )
        return jsonify({
            "status": "ok",
            "updated_at": snap["updated_at"],
            "items": enriched[:top_n],
        })
    except Exception as exc:
        logging.warning("api_social_buzz failed: %s", exc)
        return jsonify({"status": "error", "items": [], "updated_at": None})
```

- [ ] **Step 3: 서버 기동 확인**

```bash
cd "C:\Users\Administrator\Documents\카카오톡 받은 파일\종목스캐너"
python web_app/app.py &
```
Expected: `* Running on http://0.0.0.0:5000` — 에러 없이 기동

- [ ] **Step 4: 엔드포인트 응답 확인**

```bash
curl -s http://localhost:5000/api/social-buzz
```
Expected (API 키 미설정): `{"status":"disabled","items":[],"updated_at":null}`
Expected (API 키 설정 후): `{"status":"ok"|"loading","items":[...],"updated_at":"..."}`

- [ ] **Step 5: 커밋**

```bash
git add web_app/app.py
git commit -m "feat(social-buzz): /api/social-buzz 엔드포인트 + init 호출"
```

---

## Task 3: UI 위젯 (HTML + CSS + JS)

**Files:**
- Modify: `web_app/templates/scanner.html` — 위젯 HTML 추가
- Modify: `web_app/static/scanner.css` — 위젯 CSS 추가
- Modify: `web_app/static/app.js` — fetch + 렌더 함수 추가

**Interfaces:**
- Consumes: `GET /api/social-buzz`, `_stockGrade(score)` (app.js 217번 줄), `openDetail(ticker)` (app.js 기존)
- Produces: `#wsb-widget` DOM 섹션 (hidden → visible on data)

- [ ] **Step 1: `scanner.html`에 위젯 HTML 추가**

`scanner.html`의 `<!-- Macro Strip -->` 블록(`<div class="macro-strip" id="macro-strip">`) **바로 위에** 삽입:

```html
<!-- WSB 소셜 버즈 위젯 -->
<section id="wsb-widget" class="wsb-widget" hidden>
  <div class="wsb-header">
    <span class="wsb-title">🔥 오늘의 WSB 픽</span>
    <span class="wsb-updated" id="wsb-updated"></span>
  </div>
  <div class="wsb-cards" id="wsb-cards"></div>
</section>
```

- [ ] **Step 2: `scanner.css` 말미에 위젯 CSS 추가**

파일 끝에 추가:

```css
/* ── WSB 소셜 버즈 위젯 ───────────────────────────────────────────── */
.wsb-widget {
  padding: 8px 16px 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface);
}
.wsb-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.wsb-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.wsb-updated {
  font-size: 11px;
  color: var(--text-secondary);
}
.wsb-cards {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.wsb-cards::-webkit-scrollbar { display: none; }
.wsb-card {
  flex: 0 0 auto;
  min-width: 108px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  transition: background 0.12s;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wsb-card:hover { background: var(--surface-hover, #f5f5f7); }
.wsb-card-ticker {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.wsb-card-mentions {
  font-size: 11px;
  color: var(--text-secondary);
}
.wsb-sent-bar-wrap {
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
}
.wsb-sent-bar {
  height: 4px;
  background: var(--success, #16a34a);
  border-radius: 2px;
}
.wsb-empty {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 0;
}
```

- [ ] **Step 3: `app.js` 말미에 fetch + 렌더 함수 추가**

파일 끝에 추가:

```javascript
// ── WSB 소셜 버즈 위젯 ──────────────────────────────────────────────
async function loadWsbWidget() {
  const wrap     = document.getElementById('wsb-widget');
  const cardsEl  = document.getElementById('wsb-cards');
  const updEl    = document.getElementById('wsb-updated');
  if (!wrap || !cardsEl) return;

  try {
    const res  = await fetch('/api/social-buzz', { cache: 'no-store' });
    const data = await res.json();

    if (data.status === 'disabled' || data.status === 'error') {
      wrap.hidden = true;
      return;
    }
    if (data.status === 'loading') {
      cardsEl.innerHTML = '<span class="wsb-empty">데이터 로딩 중…</span>';
      wrap.hidden = false;
      return;
    }
    if (!Array.isArray(data.items) || data.items.length === 0) {
      wrap.hidden = true;
      return;
    }

    if (updEl && data.updated_at) {
      updEl.textContent = data.updated_at.replace('T', ' ').slice(0, 16) + ' UTC';
    }

    cardsEl.innerHTML = data.items.map(item => {
      const grade    = item.total_score != null ? _stockGrade(item.total_score) : null;
      const gradeHtml = grade
        ? `<span class="grade-badge grade-${grade}">${grade}</span>`
        : '';
      const sentPct  = Math.min(100, Math.round((item.sentiment || 0) * 100));
      const ticker   = String(item.ticker).replace(/[^A-Z0-9.]/g, '');
      return `<div class="wsb-card" data-ticker="${ticker}" onclick="openDetail('${ticker}')">
        <div class="wsb-card-ticker">${ticker}</div>
        <div class="wsb-card-mentions">${item.mentions} mentions</div>
        <div class="wsb-sent-bar-wrap" title="긍정 감성 ${sentPct}%">
          <div class="wsb-sent-bar" style="width:${sentPct}%"></div>
        </div>
        ${gradeHtml}
      </div>`;
    }).join('');

    wrap.hidden = false;
  } catch (err) {
    console.warn('[wsb] fetch failed', err);
    if (wrap) wrap.hidden = true;
  }
}

document.addEventListener('DOMContentLoaded', loadWsbWidget);
```

- [ ] **Step 4: 브라우저에서 위젯 확인**

서버 재기동 후 `http://localhost:5000` 접속:
- `SWAGGY_API_KEY` 미설정 → 위젯 숨김 (hidden 유지) 확인
- `SWAGGY_API_KEY` 설정 후 → 위젯 렌더 확인 (또는 "데이터 로딩 중…" 표시)
- 카드 클릭 → 기존 종목 상세 드로어 열림 확인

- [ ] **Step 5: 커밋**

```bash
git add web_app/templates/scanner.html web_app/static/scanner.css web_app/static/app.js
git commit -m "feat(social-buzz): WSB 픽 위젯 UI (HTML + CSS + JS)"
```

---

## 셀프 리뷰 체크리스트

- [x] **스펙 커버리지**
  - WSB 언급량 필터: Task 1 `_filter()` ✓
  - 감성 필터: Task 1 `_filter()` ✓
  - TotalScore 정렬: Task 2 `enriched.sort()` ✓
  - 30분 캐시: Task 1 `_bg_loop()` + `_REFRESH_SEC` ✓
  - API 장애 fallback: Task 1 `refresh()` except 블록 ✓
  - 메인 페이지 위젯: Task 3 ✓
  - `SWAGGY_API_KEY` 없으면 비활성화: Task 2 `disabled` 처리 ✓
  - 카드 클릭 → 드로어: Task 3 `openDetail()` ✓

- [x] **플레이스홀더 없음**: 모든 코드 블록 완성

- [x] **타입 일관성**:
  - `get_cached()` → `dict` (Task 1 정의, Task 2에서 사용)
  - `items` 원소: `{ticker: str, mentions: int, sentiment: float}` (Task 1 → Task 2 → Task 3)
  - `total_score`: `float | None` (Task 2에서 병합, Task 3 JS에서 `_stockGrade` 호출)
