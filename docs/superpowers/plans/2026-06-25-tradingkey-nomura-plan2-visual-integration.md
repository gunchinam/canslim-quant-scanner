# TradingKey + 노무라式 Plan 2 — 시각 통합

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan 1의 데이터 파운데이션 위에 UI를 구축한다 — 드로어에 노무라式 탭(4개 아코디언 섹션), handdrawn_renderer.py에 Fibonacci/S/R 레이어와 원형 게이지 배지를 추가한다.

**Architecture:**
- `detail.html` + `app.js`: 새 "노무라式" 탭 + lazy-load 아코디언 4개 섹션 (TK Score, 노무라式 스코어, 기관 투자자, Football Field 히트맵)
- `handdrawn_renderer.py`: Fibonacci/S/R 수평선 레이어, 노무라式 원형 게이지 배지 (matplotlib)
- `web_app/app.py`: 차트 렌더 시 `get_support_resistance()` + `get_nomura_score()` 데이터 주입

**Tech Stack:** Vanilla JS (ES2020), HTML5 `<details>`/`<summary>`, CSS custom properties, matplotlib patches, SVG (inline JS-generated)

## Global Constraints

- 브랜드: **노무라式** (노무라 아님)
- KR 종목에서는 노무라式 탭 자체를 숨긴다 (JS에서 `window.MARKET !== 'KR'` 체크)
- 신규 JS 함수는 기존 `loadUSInsight()` 패턴을 따른다 (lazy-load, once 플래그)
- 신규 Python 파라미터는 모두 선택적(기본값 None/False)으로 — 기존 코드 무변경 보장
- `handdrawn_renderer.py` 변경 후 기존 테스트(`tests/test_nomura_score.py`, `tests/test_tradingkey_api.py`) 계속 통과
- Python 테스트: `.venv64\Scripts\python -m pytest`
- Flask/UI 테스트: system Python `python -m pytest`

---

### Task 1: detail.html + CSS — 노무라式 탭 + 아코디언 골격

**Files:**
- Modify: `web_app/templates/detail.html`
- Modify: `web_app/static/scanner.css` (또는 `theme.css`; 아코디언 CSS 추가)

**Interfaces:**
- Produces: `#tab-nomura` 패널 ID, 4개 아코디언 `<details>` element IDs:
  - `#nm-acc-tkscore` — TK Score
  - `#nm-acc-nomura` — 노무라式 스코어
  - `#nm-acc-institution` — 기관 투자자
  - `#nm-acc-football` — Football Field
- Produces: 탭 버튼 `#btn-nomura` (onclick=`switchTab('nomura')`)
- Produces: 로딩 스피너 `#nm-loading`, 에러 `#nm-error`

- [ ] **Step 1: 탭 버튼 추가**

`web_app/templates/detail.html`의 `<nav class="tab-nav">` 안에 마지막 버튼 앞에 추가:

```html
<button class="tab-btn" role="tab" aria-selected="false"
        aria-controls="tab-nomura" id="btn-nomura"
        onclick="switchTab('nomura')" style="display:none;">노무라式</button>
```

- [ ] **Step 2: 탭 패널 추가**

`</div><!-- end scroll-content -->` 바로 앞, 마지막 탭 패널 다음에 추가:

```html
<!-- 노무라式 Tab (US only) -->
<div class="tab-panel" id="tab-nomura" role="tabpanel" aria-labelledby="btn-nomura">
  <div style="padding:12px 16px 4px;">
    <div id="nm-loading" style="text-align:center;padding:20px;color:var(--text-tertiary);font-size:13px;">로딩 중…</div>
    <div id="nm-error" style="display:none;text-align:center;padding:20px;color:var(--destructive);font-size:13px;"></div>

    <!-- TK Score 아코디언 (기본: 펼침) -->
    <details id="nm-acc-tkscore" class="nm-accordion" open>
      <summary class="nm-acc-summary">
        <span class="nm-acc-icon">📊</span>
        <span class="nm-acc-title">TK Score</span>
        <span class="nm-acc-chevron">▾</span>
      </summary>
      <div class="nm-acc-body" id="nm-tkscore-body">
        <div class="nm-placeholder">—</div>
      </div>
    </details>

    <!-- 노무라式 스코어 아코디언 (기본: 접힘) -->
    <details id="nm-acc-nomura" class="nm-accordion">
      <summary class="nm-acc-summary">
        <span class="nm-acc-icon">🏦</span>
        <span class="nm-acc-title">노무라式 스코어 &amp; 레이팅</span>
        <span class="nm-acc-chevron">▾</span>
      </summary>
      <div class="nm-acc-body" id="nm-nomura-body">
        <div class="nm-placeholder">—</div>
      </div>
    </details>

    <!-- 기관 투자자 아코디언 (기본: 접힘) -->
    <details id="nm-acc-institution" class="nm-accordion">
      <summary class="nm-acc-summary">
        <span class="nm-acc-icon">🏛</span>
        <span class="nm-acc-title">기관 투자자 현황</span>
        <span class="nm-acc-chevron">▾</span>
      </summary>
      <div class="nm-acc-body" id="nm-institution-body">
        <div class="nm-placeholder">—</div>
      </div>
    </details>

    <!-- Football Field 아코디언 (기본: 접힘) -->
    <details id="nm-acc-football" class="nm-accordion">
      <summary class="nm-acc-summary">
        <span class="nm-acc-icon">⚽</span>
        <span class="nm-acc-title">Football Field 밸류에이션</span>
        <span class="nm-acc-chevron">▾</span>
      </summary>
      <div class="nm-acc-body" id="nm-football-body">
        <div class="nm-placeholder">—</div>
      </div>
    </details>
  </div>
  <div style="height:24px;"></div>
</div>
```

- [ ] **Step 3: CSS 추가**

`web_app/static/scanner.css` 끝에 추가:

```css
/* ── 노무라式 아코디언 ─────────────────────────────────────────── */
.nm-accordion {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  overflow: hidden;
}
.nm-acc-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  cursor: pointer;
  list-style: none;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  user-select: none;
}
.nm-acc-summary::-webkit-details-marker { display: none; }
.nm-acc-icon { font-size: 15px; }
.nm-acc-title { flex: 1; }
.nm-acc-chevron {
  font-size: 12px;
  color: var(--text-tertiary);
  transition: transform 0.18s ease;
}
details[open] .nm-acc-chevron { transform: rotate(180deg); }
.nm-acc-body {
  padding: 0 14px 12px;
  font-size: 12px;
  color: var(--text-secondary);
}
.nm-placeholder { color: var(--text-tertiary); font-size: 12px; }

/* TK Score 그리드 */
.nm-score-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.nm-score-cell {
  background: var(--surface-subtle);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nm-score-label { font-size: 10px; color: var(--text-tertiary); }
.nm-score-val { font-size: 16px; font-weight: 800; color: var(--text-primary); }

/* Football Field 히트맵 바 */
.ff-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ff-label { font-size: 11px; color: var(--text-tertiary); width: 110px; flex-shrink: 0; }
.ff-bar-wrap {
  flex: 1;
  height: 16px;
  border-radius: 8px;
  background: linear-gradient(to right, #22c55e, #facc15, #ef4444);
  position: relative;
}
.ff-marker {
  position: absolute;
  top: -3px;
  width: 6px;
  height: 22px;
  background: var(--text-primary);
  border-radius: 2px;
  transform: translateX(-50%);
}
.ff-tag { font-size: 10px; color: var(--text-tertiary); width: 44px; text-align: right; }
```

- [ ] **Step 4: 변경 검증**

브라우저에서 `/detail/AAPL` 로드 → 탭이 4개인 것 확인 (노무라式 탭은 아직 숨겨짐)
HTML validator로 `<details>/<summary>` 중첩 오류 없는지 확인

- [ ] **Step 5: Commit**

```bash
git add web_app/templates/detail.html web_app/static/scanner.css
git commit -m "feat(ui): 노무라式 탭 + 아코디언 4섹션 골격 추가"
```

---

### Task 2: app.js — loadNomuraScore() + TK Score 섹션 렌더링

**Files:**
- Modify: `web_app/static/app.js`

**Interfaces:**
- Consumes: `GET /api/nomura-score/<ticker>` → `{status:"ok", data:{quantitative_score, grade, piotroski, altman_z, beneish_m, beneish_warning, nomura_rating, nomura_target, nomura_upside}}` OR `{status:"error"}` OR TradingKey `data.tk` (score.overall, score.valuation, score.growth, score.profitability, score.momentum, score.risk)
- Consumes: `GET /api/ticker/<ticker>` TK data via existing `loadTKScore()` call (see existing `loadUSInsight` pattern)
- Produces: `loadNomuraScore(ticker)` function, `_nmLoaded` flag
- Produces: TK Score grid populated in `#nm-tkscore-body`

Note: `/api/nomura-score/<ticker>` returns nomura score only. For TK Score (7-layer), call `/api/tradingkey/<ticker>` if it exists, or use the `data` field from `/api/ticker/<ticker>`. Check existing routes. If no dedicated TK endpoint, show only the nomura data in the TK Score section.

- [ ] **Step 1: loadNomuraScore 함수 추가**

`app.js`에서 `loadUSInsight` 함수 아래에 추가:

```javascript
let _nmLoaded = false;

async function loadNomuraScore(ticker) {
  if (_nmLoaded) return;
  _nmLoaded = true;

  const loading = document.getElementById('nm-loading');
  const errEl   = document.getElementById('nm-error');
  if (loading) loading.style.display = '';
  if (errEl)   errEl.style.display   = 'none';

  try {
    const res  = await fetch(`/api/nomura-score/${encodeURIComponent(ticker)}`);
    const json = await res.json();
    if (!res.ok || json.status !== 'ok') throw new Error(json.message || `HTTP ${res.status}`);
    if (loading) loading.style.display = 'none';
    _renderNomuraTKScore(json.data);
    _renderNomuraScore(json.data);
  } catch (e) {
    if (loading) loading.style.display = 'none';
    if (errEl) {
      errEl.textContent = `노무라式 데이터 로드 실패: ${e.message}`;
      errEl.style.display = '';
    }
  }
}
```

- [ ] **Step 2: TK Score 렌더 함수 추가**

```javascript
function _renderNomuraTKScore(d) {
  const body = document.getElementById('nm-tkscore-body');
  if (!body) return;
  // quantitative_score를 TK Score 섹션에 전체 점수로 표시
  // nomura_rating, grade도 함께 표시
  const score = d.quantitative_score ?? '—';
  const grade = d.grade ?? '—';
  const rating = d.nomura_rating ?? '—';

  const ratingColor = {
    'Conviction Buy': 'var(--brand)',
    'Buy': 'var(--success)',
    'Neutral': 'var(--text-secondary)',
    'Reduce': 'var(--destructive)',
    'Sell': 'var(--destructive)',
  }[rating] || 'var(--text-primary)';

  body.innerHTML = `
    <div class="nm-score-grid">
      <div class="nm-score-cell">
        <span class="nm-score-label">종합 점수</span>
        <span class="nm-score-val">${score}</span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">등급</span>
        <span class="nm-score-val">${esc(grade)}</span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">레이팅</span>
        <span class="nm-score-val" style="color:${ratingColor};font-size:12px">${esc(rating)}</span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">목표가</span>
        <span class="nm-score-val" style="font-size:13px">${d.nomura_target ? '$' + d.nomura_target.toFixed(2) : '—'}</span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">업사이드</span>
        <span class="nm-score-val" style="font-size:13px;color:${(d.nomura_upside||0)>=0?'var(--success)':'var(--destructive)'}">
          ${d.nomura_upside != null ? (d.nomura_upside >= 0 ? '+' : '') + d.nomura_upside.toFixed(1) + '%' : '—'}
        </span>
      </div>
    </div>`;
}
```

- [ ] **Step 3: switchTab에 노무라式 탭 연결**

`switchTab` 함수 안에서 `'usinsight'` 처리 부분 아래에 추가 (기존 패턴 참고):

```javascript
if (tabId === 'nomura' && typeof TICKER !== 'undefined' && TICKER) {
  loadNomuraScore(TICKER);
}
```

- [ ] **Step 4: US 종목일 때 탭 버튼 노출**

기존에서 `btn-usinsight`를 표시하는 코드 근처에 추가 (US 종목 감지 후):

```javascript
const nmBtn = document.getElementById('btn-nomura');
if (nmBtn && market === 'US') nmBtn.style.display = '';
```

(기존 코드에서 `market` 값이 어떻게 전달되는지 확인 후 동일한 조건 사용)

- [ ] **Step 5: Commit**

```bash
git add web_app/static/app.js
git commit -m "feat(ui): loadNomuraScore() + TK Score 섹션 렌더링"
```

---

### Task 3: app.js — 노무라式 스코어 섹션 (SVG 게이지 + KPI)

**Files:**
- Modify: `web_app/static/app.js`

**Interfaces:**
- Consumes: same `d` object from `loadNomuraScore` (piotroski, altman_z, beneish_m, beneish_warning, quantitative_score, nomura_rating)
- Produces: `_renderNomuraScore(d)` function
- Produces: SVG 원형 게이지 in `#nm-nomura-body`

- [ ] **Step 1: SVG 게이지 헬퍼 함수 추가**

```javascript
function _nmGaugeSVG(score, rating) {
  const r = 28;
  const circ = 2 * Math.PI * r;            // ≈ 175.9
  const filled = (score / 100) * circ;
  const ratingColors = {
    'Conviction Buy': '#3b82f6',
    'Buy': '#22c55e',
    'Neutral': '#eab308',
    'Reduce': '#f97316',
    'Sell': '#ef4444',
  };
  const color = ratingColors[rating] || '#94a3b8';
  const shortRating = {'Conviction Buy':'C.BUY','Buy':'BUY','Neutral':'NTRL','Reduce':'RDCE','Sell':'SELL'}[rating] || rating;
  return `<svg viewBox="0 0 72 72" width="80" height="80">
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="#1e293b" stroke-width="6"/>
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="${color}" stroke-width="6"
      stroke-dasharray="${filled.toFixed(1)} ${circ.toFixed(1)}" stroke-dashoffset="${(circ * 0.25).toFixed(1)}"
      stroke-linecap="round" transform="rotate(-90 36 36)"/>
    <text x="36" y="30" text-anchor="middle" font-size="7" fill="#64748b" font-weight="700">노무라式</text>
    <text x="36" y="42" text-anchor="middle" font-size="11" fill="${color}" font-weight="900">${esc(shortRating)}</text>
    <text x="36" y="52" text-anchor="middle" font-size="8" fill="#94a3b8">${score}/100</text>
  </svg>`;
}
```

- [ ] **Step 2: 노무라式 스코어 섹션 렌더 함수 추가**

```javascript
function _renderNomuraScore(d) {
  const body = document.getElementById('nm-nomura-body');
  if (!body) return;

  const score   = d.quantitative_score ?? 0;
  const rating  = d.nomura_rating ?? '—';
  const pio     = d.piotroski    ?? '—';
  const az      = d.altman_z     != null ? d.altman_z.toFixed(2)  : '—';
  const bm      = d.beneish_m    != null ? d.beneish_m.toFixed(2) : '—';
  const bWarn   = d.beneish_warning;

  const azColor = d.altman_z != null
    ? (d.altman_z > 2.99 ? 'var(--success)' : d.altman_z > 1.81 ? '#eab308' : 'var(--destructive)')
    : 'var(--text-secondary)';
  const azLabel = d.altman_z != null
    ? (d.altman_z > 2.99 ? '안전' : d.altman_z > 1.81 ? '회색지대' : '위험')
    : '';

  body.innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;">
      ${_nmGaugeSVG(score, rating)}
      <div>
        <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:4px;">정량 분석 스코어</div>
        <div style="font-size:22px;font-weight:900;color:var(--text-primary);">${score}<span style="font-size:13px;font-weight:400;color:var(--text-tertiary);">/100</span></div>
      </div>
    </div>
    <div class="nm-score-grid">
      <div class="nm-score-cell">
        <span class="nm-score-label">Piotroski</span>
        <span class="nm-score-val">${pio}<span style="font-size:10px;font-weight:400;color:var(--text-tertiary);">/9</span></span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">Altman Z</span>
        <span class="nm-score-val" style="color:${azColor};font-size:13px">${az} <span style="font-size:9px;">${azLabel}</span></span>
      </div>
      <div class="nm-score-cell">
        <span class="nm-score-label">Beneish M</span>
        <span class="nm-score-val" style="color:${bWarn ? 'var(--destructive)' : 'var(--success)'};font-size:13px">
          ${bm} ${bWarn ? '⚠️' : '✓'}
        </span>
      </div>
    </div>`;
}
```

- [ ] **Step 3: 기관 투자자 섹션 렌더 함수 추가**

이 함수는 TradingKey `institutional` 데이터를 필요로 한다. `/api/nomura-score/<ticker>` 응답에는 포함되지 않으므로, 섹션을 열 때 `/api/tradingkey/<ticker>`를 별도로 호출하거나, 현재는 `—` placeholder로 표시하고 Task 4에서 Football Field와 함께 TK 데이터 로드를 추가한다.

기관 투자자 섹션을 `<details ontoggle>` 이벤트로 lazy-load:

```javascript
function _initNomuraInstitutionAccordion(ticker) {
  const acc = document.getElementById('nm-acc-institution');
  if (!acc) return;
  let loaded = false;
  acc.addEventListener('toggle', async () => {
    if (!acc.open || loaded) return;
    loaded = true;
    const body = document.getElementById('nm-institution-body');
    if (!body) return;
    body.innerHTML = '<div class="nm-placeholder">로딩 중…</div>';
    try {
      // TK data comes from existing /api/ticker endpoint (institutional field)
      const res  = await fetch(`/api/ticker/${encodeURIComponent(ticker)}`);
      const json = await res.json();
      const inst = json?.tradingkey?.institutional;
      if (!inst) throw new Error('기관 데이터 없음');
      const qoqColor = (inst.holding_qoq || 0) >= 0 ? 'var(--success)' : 'var(--destructive)';
      body.innerHTML = `
        <div class="nm-score-grid">
          <div class="nm-score-cell">
            <span class="nm-score-label">기관 비중</span>
            <span class="nm-score-val" style="font-size:13px">${inst.holding_pct != null ? inst.holding_pct.toFixed(1) + '%' : '—'}</span>
          </div>
          <div class="nm-score-cell">
            <span class="nm-score-label">QoQ 변화</span>
            <span class="nm-score-val" style="color:${qoqColor};font-size:13px">
              ${inst.holding_qoq != null ? (inst.holding_qoq >= 0 ? '+' : '') + inst.holding_qoq.toFixed(1) + '%' : '—'}
            </span>
          </div>
          <div class="nm-score-cell">
            <span class="nm-score-label">최대 보유사</span>
            <span class="nm-score-val" style="font-size:11px">${inst.top_holder ? esc(inst.top_holder) : '—'}</span>
          </div>
        </div>`;
    } catch (e) {
      body.innerHTML = `<div class="nm-placeholder">기관 데이터 없음 (${esc(e.message)})</div>`;
    }
  });
}
```

- [ ] **Step 4: loadNomuraScore에서 기관 accordion 초기화 호출**

`loadNomuraScore` 함수 안 `_renderNomuraScore(json.data)` 다음 줄에:
```javascript
_initNomuraInstitutionAccordion(ticker);
```

- [ ] **Step 5: Commit**

```bash
git add web_app/static/app.js
git commit -m "feat(ui): 노무라式 스코어 섹션 SVG 게이지 + 기관 투자자 lazy-load"
```

---

### Task 4: app.js — Football Field 히트맵 섹션

**Files:**
- Modify: `web_app/static/app.js`

**Interfaces:**
- Consumes: `d.nomura_target` (목표가), current price from existing detail data
- Produces: `_initNomuraFootballField(ticker, currentPrice)` 함수
- Produces: Football Field 4개 히트맵 바 in `#nm-football-body`

Football Field 4개 방법론:
1. PER 섹터 비교: TK `score.valuation` (0-100) → 위치 = valuation/100
2. 애널리스트 목표가: TK `analyst.target_price` vs current price
3. TK 지지선/저항선: `nomura_target` vs support/resistance range
4. 기술적 위치: `risk_technical.reward_risk` 정규화

- [ ] **Step 1: Football Field 렌더 헬퍼 함수**

```javascript
function _ffBar(label, pct, tag) {
  // pct: 0~1 (왼쪽=저평가, 오른쪽=고평가)
  const safePct = Math.max(0, Math.min(1, pct || 0));
  return `<div class="ff-row">
    <span class="ff-label">${esc(label)}</span>
    <div class="ff-bar-wrap">
      <div class="ff-marker" style="left:${(safePct * 100).toFixed(1)}%"></div>
    </div>
    <span class="ff-tag">${esc(tag || '')}</span>
  </div>`;
}

function _initNomuraFootballField(ticker, currentPrice) {
  const acc = document.getElementById('nm-acc-football');
  if (!acc) return;
  let loaded = false;
  acc.addEventListener('toggle', async () => {
    if (!acc.open || loaded) return;
    loaded = true;
    const body = document.getElementById('nm-football-body');
    if (!body) return;
    body.innerHTML = '<div class="nm-placeholder">로딩 중…</div>';
    try {
      const res  = await fetch(`/api/nomura-score/${encodeURIComponent(ticker)}`);
      const json = await res.json();
      if (!res.ok || json.status !== 'ok') throw new Error(json.message || 'error');
      const d = json.data;
      let html = '<div style="margin-top:4px;">';

      // 1) 노무라式 종합 점수 기반 (점수가 높을수록 우측 = 고평가 아닌 고품질로 해석)
      const scorePct = (d.quantitative_score || 0) / 100;
      const scoreTag = d.quantitative_score >= 75 ? '고품질' : d.quantitative_score >= 55 ? '보통' : '저품질';
      html += _ffBar('노무라式 점수', scorePct, scoreTag);

      // 2) 목표가 업사이드 (양수 = 저평가, 음수 = 고평가)
      if (d.nomura_upside != null) {
        // upside: +30% → 저평가(왼쪽 0.2), -10% → 고평가(오른쪽 0.8)
        const upPct = 0.5 - (d.nomura_upside / 100) * 0.5;
        const upTag = d.nomura_upside >= 10 ? '저평가' : d.nomura_upside >= 0 ? '적정' : '고평가';
        html += _ffBar('목표가 업사이드', Math.max(0.05, Math.min(0.95, upPct)), upTag);
      }

      // 3) Piotroski (높을수록 좋음, 왼쪽 = 저품질 = 저평가 영역으로 해석 안 함 → 품질 척도)
      if (d.piotroski != null) {
        const pioPct = d.piotroski / 9;
        const pioTag = `F${d.piotroski}`;
        html += _ffBar('Piotroski F-Score', pioPct, pioTag);
      }

      // 4) Altman Z (>2.99 안전=왼쪽 저위험, <1.81 위험=오른쪽 고위험)
      if (d.altman_z != null) {
        // map: [0, 3+] → [1, 0] (높을수록 왼쪽=안전)
        const azPct = 1 - Math.min(1, Math.max(0, d.altman_z / 4));
        const azTag = d.altman_z > 2.99 ? '안전' : d.altman_z > 1.81 ? '회색' : '위험';
        html += _ffBar('Altman Z (리스크)', azPct, azTag);
      }

      html += '</div>';
      html += '<div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-tertiary);margin-top:4px;padding:0 2px;"><span>← 긍정</span><span>부정 →</span></div>';
      body.innerHTML = html;
    } catch (e) {
      body.innerHTML = `<div class="nm-placeholder">Football Field 로드 실패: ${esc(e.message)}</div>`;
    }
  });
}
```

- [ ] **Step 2: loadNomuraScore에서 Football Field 초기화 호출**

`_initNomuraInstitutionAccordion(ticker)` 다음에:
```javascript
_initNomuraFootballField(ticker, null);
```

- [ ] **Step 3: Commit**

```bash
git add web_app/static/app.js
git commit -m "feat(ui): Football Field 히트맵 섹션 (4개 지표)"
```

---

### Task 5: handdrawn_renderer.py — Fibonacci + S/R 레이어

**Files:**
- Modify: `handdrawn_renderer.py`
- Create: `tests/test_handdrawn_layers.py`

**Interfaces:**
- Produces: `HandDrawnChartRenderer.__init__` 신규 파라미터:
  - `support: float | None = None`
  - `resistance: float | None = None`
  - `show_fib: bool = True`
  - `show_sr: bool = True`
- Produces: `render()` 내에서 Fibonacci 수평선, S/R 수평선을 `ax_price`에 추가

Fibonacci 레벨: 조회 기간 내 `hist['High'].max()`, `hist['Low'].min()` → 0.236, 0.382, 0.5, 0.618, 0.786

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_handdrawn_layers.py` 생성:

```python
import numpy as np
import pandas as pd
import pytest

def _make_hist(n=60):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.01,
        "Low":  close * 0.98,
        "Close": close,
        "Volume": np.ones(n) * 1_000_000,
    }, index=dates)
    return df

class _DummyResult:
    def to_dict(self): return {}
    annotations: list = []
    phase = "bull"

def test_renderer_fib_layers_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        show_fib=True, show_sr=True,
        support=95.0, resistance=110.0,
    )
    img = r.render()
    assert img is not None
    assert img.width > 0

def test_renderer_fib_disabled_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        show_fib=False, show_sr=False,
    )
    img = r.render()
    assert img is not None

def test_renderer_backward_compat():
    """기존 코드처럼 신규 파라미터 없이 호출해도 동작해야 한다."""
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    r = HandDrawnChartRenderer(hist, _DummyResult(), ticker="AAPL")
    img = r.render()
    assert img is not None
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```
.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py -v
```
예상: `TypeError: __init__() got unexpected keyword argument 'show_fib'`

- [ ] **Step 3: __init__에 신규 파라미터 추가**

`HandDrawnChartRenderer.__init__` 시그니처 변경:

```python
def __init__(self, hist: pd.DataFrame, result: FourAxisResult,
             ticker: str = "", lookback: int = 120,
             width_px: int = 720, height_px: int = 600, dpi: int = 100,
             support: float | None = None,
             resistance: float | None = None,
             show_fib: bool = True,
             show_sr: bool = True):
```

`__init__` 본문 끝(기존 마지막 줄 다음)에:
```python
        self._support    = support
        self._resistance = resistance
        self._show_fib   = show_fib
        self._show_sr    = show_sr
```

- [ ] **Step 4: render()에 Fibonacci 레이어 추가**

`render()` 안에서 가격 패널 그리기 블록이 끝난 직후 (`ax_vol` 그리기 시작 전)에 추가:

```python
            # ── ⑤ Fibonacci 수평선 ─────────────────────────────────
            if self._show_fib and len(self.hist) > 1:
                h_max = self.hist["High"].max()
                h_min = self.hist["Low"].min()
                fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
                fib_colors = ["#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6"]
                for lvl, col in zip(fib_levels, fib_colors):
                    price = h_min + (h_max - h_min) * lvl
                    ax_price.axhline(price, color=col, linewidth=0.8 * lw_scale,
                                     linestyle=(0, (5, 4)), alpha=0.55)
                    ax_price.text(len(x) - 1, price, f" {lvl:.3f}",
                                  fontsize=max(6, int(fs_tick * 0.75)),
                                  color=col, va="center", alpha=0.7,
                                  transform=ax_price.get_yaxis_transform() if False else ax_price.transData)

            # ── ⑥ S/R 수평점선 ─────────────────────────────────────
            if self._show_sr:
                if self._support is not None:
                    ax_price.axhline(self._support, color="#22c55e",
                                     linewidth=1.2 * lw_scale, linestyle="--", alpha=0.7)
                    ax_price.text(0, self._support, "S ", fontsize=max(6, int(fs_tick * 0.8)),
                                  color="#22c55e", va="bottom", ha="left", alpha=0.8)
                if self._resistance is not None:
                    ax_price.axhline(self._resistance, color="#ef4444",
                                     linewidth=1.2 * lw_scale, linestyle="--", alpha=0.7)
                    ax_price.text(0, self._resistance, "R ", fontsize=max(6, int(fs_tick * 0.8)),
                                  color="#ef4444", va="top", ha="left", alpha=0.8)
```

- [ ] **Step 5: 테스트 실행 — PASS 확인**

```
.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py -v
```
예상: 3/3 PASS

- [ ] **Step 6: Commit**

```bash
git add handdrawn_renderer.py tests/test_handdrawn_layers.py
git commit -m "feat(chart): Fibonacci + S/R 레이어 추가 (show_fib, show_sr, support, resistance 파라미터)"
```

---

### Task 6: handdrawn_renderer.py — 노무라式 배지 + app.py 차트 통합

**Files:**
- Modify: `handdrawn_renderer.py`
- Modify: `web_app/app.py`
- Modify: `tests/test_handdrawn_layers.py` (테스트 추가)

**Interfaces:**
- Consumes: `get_support_resistance(ticker) -> tuple[float, float] | None` from `tradingkey_api`
- Consumes: `get_nomura_score(ticker) -> dict | None` from `nomura_score`
- Produces: `HandDrawnChartRenderer.__init__` 신규 파라미터:
  - `nomura_score_data: dict | None = None` (9-key dict from `get_nomura_score`)
- Produces: 원형 게이지 배지를 차트 우상단에 그리는 `_draw_nomura_badge()` 메서드
- Produces: `app.py` `_compute_four_axis_payload()` 에서 TK + nomura 데이터 주입

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_handdrawn_layers.py`에 추가:

```python
def test_renderer_nomura_badge_no_crash():
    from handdrawn_renderer import HandDrawnChartRenderer
    hist = _make_hist()
    nomura_data = {
        "quantitative_score": 82,
        "grade": "A",
        "piotroski": 7,
        "altman_z": 3.5,
        "beneish_m": -2.1,
        "beneish_warning": False,
        "nomura_rating": "Buy",
        "nomura_target": 200.0,
        "nomura_upside": 12.5,
    }
    r = HandDrawnChartRenderer(
        hist, _DummyResult(), ticker="TEST",
        nomura_score_data=nomura_data,
    )
    img = r.render()
    assert img is not None
    assert img.width > 0
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```
.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py::test_renderer_nomura_badge_no_crash -v
```
예상: `TypeError`

- [ ] **Step 3: __init__에 nomura_score_data 파라미터 추가**

`__init__` 시그니처에 추가:
```python
             nomura_score_data: dict | None = None):
```

`__init__` 본문 끝에:
```python
        self._nomura_score_data = nomura_score_data
```

- [ ] **Step 4: _draw_nomura_badge() 메서드 추가**

`HandDrawnChartRenderer` 클래스 안 (render 메서드 위)에 추가:

```python
    def _draw_nomura_badge(self, ax, score: int, rating: str, lw_scale: float):
        """우상단에 원형 게이지 배지를 그린다."""
        from matplotlib.patches import Arc, FancyBboxPatch
        from matplotlib.transforms import Bbox

        rating_colors = {
            "Conviction Buy": "#3b82f6",
            "Buy": "#22c55e",
            "Neutral": "#eab308",
            "Reduce": "#f97316",
            "Sell": "#ef4444",
        }
        color = rating_colors.get(rating, "#94a3b8")
        short = {"Conviction Buy": "C.BUY", "Buy": "BUY",
                 "Neutral": "NTRL", "Reduce": "RDCE", "Sell": "SELL"}.get(rating, rating[:4])

        # inset axes: 우상단 0.12×0.20 비율
        ax_inset = ax.inset_axes([0.80, 0.76, 0.18, 0.22])
        ax_inset.set_xlim(0, 1)
        ax_inset.set_ylim(0, 1)
        ax_inset.axis("off")
        ax_inset.set_facecolor("#0f1117")

        # 배경 원
        bg = plt.Circle((0.5, 0.5), 0.42, color="#1e293b", zorder=1)
        ax_inset.add_patch(bg)

        # 게이지 호 (score/100 비율)
        angle = score / 100 * 360
        gauge = Arc((0.5, 0.5), 0.80, 0.80, angle=90,
                    theta1=-angle, theta2=0,
                    color=color, linewidth=3 * lw_scale, zorder=2)
        ax_inset.add_patch(gauge)

        # 텍스트
        ax_inset.text(0.5, 0.68, "노무라式", ha="center", va="center",
                      fontsize=5, color="#64748b", fontweight="bold", zorder=3)
        ax_inset.text(0.5, 0.50, short, ha="center", va="center",
                      fontsize=7, color=color, fontweight="black", zorder=3)
        ax_inset.text(0.5, 0.30, f"{score}", ha="center", va="center",
                      fontsize=6, color="#94a3b8", zorder=3)
```

- [ ] **Step 5: render()에서 배지 호출 추가**

S/R 레이어 코드 다음에 추가:

```python
            # ── ⑨ 노무라式 배지 ─────────────────────────────────────
            if self._nomura_score_data:
                _nm = self._nomura_score_data
                _score  = _nm.get("quantitative_score", 0) or 0
                _rating = _nm.get("nomura_rating", "")  or ""
                try:
                    self._draw_nomura_badge(ax_price, _score, _rating, lw_scale)
                except Exception as _badge_err:
                    logging.debug("nomura badge draw failed: %s", _badge_err)
```

- [ ] **Step 6: app.py — _compute_four_axis_payload 업데이트**

`_compute_four_axis_payload` 함수에서 `HandDrawnChartRenderer(...)` 호출 부분을 찾아 수정:

기존:
```python
            renderer = HandDrawnChartRenderer(
                hist, result, ticker=chart_title,
                width_px=1200, height_px=560, dpi=100,
            )
```

변경:
```python
            _sr_data      = None
            _nomura_data  = None
            if market == "US":
                try:
                    from tradingkey_api import get_support_resistance
                    _sr_data = get_support_resistance(ticker)
                except Exception:
                    pass
                try:
                    from nomura_score import get_nomura_score
                    _nomura_data = get_nomura_score(ticker)
                except Exception:
                    pass

            renderer = HandDrawnChartRenderer(
                hist, result, ticker=chart_title,
                width_px=1200, height_px=560, dpi=100,
                support=_sr_data[0] if _sr_data else None,
                resistance=_sr_data[1] if _sr_data else None,
                show_fib=True,
                show_sr=_sr_data is not None,
                nomura_score_data=_nomura_data,
            )
```

- [ ] **Step 7: 테스트 실행 — PASS 확인**

```
.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py -v
```
예상: 4/4 PASS

- [ ] **Step 8: Commit**

```bash
git add handdrawn_renderer.py web_app/app.py tests/test_handdrawn_layers.py
git commit -m "feat(chart): 노무라式 원형 배지 + app.py TK/nomura 데이터 주입"
```

---

## 테스트 요약

| Task | 테스트 방법 | 기대 결과 |
|------|------------|-----------|
| Task 1 | 브라우저 `/detail/AAPL` 로드 | 탭 구조 정상, 아코디언 열림/닫힘 |
| Task 2 | 브라우저 + Network 탭 | `/api/nomura-score/AAPL` 호출, TK Score 그리드 표시 |
| Task 3 | 브라우저 | SVG 게이지 렌더링, KPI 그리드 표시 |
| Task 4 | 브라우저 | Football Field 4개 바 + 마커 표시 |
| Task 5 | `.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py` | 3/3 PASS |
| Task 6 | `.venv64\Scripts\python -m pytest tests/test_handdrawn_layers.py` | 4/4 PASS |

---

## 참고: 변수명 충돌 방지

기존 app.js에 `NomuraTarget`, `NomuraMethod`, `NomuraBias`, `NomuraUsed` 변수명이 있다.
이들은 **DCF 밸류에이션 엔진**의 목표가이며, 이번에 추가하는 **노무라式 스코어링** 시스템과는 별개다.
신규 JS 변수/함수는 `_nm` 접두사를 사용해 충돌을 방지한다.
