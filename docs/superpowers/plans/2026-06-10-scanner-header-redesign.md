# 종목 스캐너 상단 헤더 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 스캐너 상단 6개 띠를 "TopBar / 탭+Stats / 컨텍스트 바 / 필터칩" 4줄로 압축하고, "종목 스캐너"를 brand색 대형 세그먼트 탭으로 또렷하게 만든다.

**Architecture:** 순수 프론트엔드 재구성 — `scanner.html` DOM 재배치 + `scanner.css` 스타일. JS는 변경하지 않고 기존 ID·`data-action`을 모두 보존해 핸들러가 그대로 동작하게 한다. 취약한 `.app-shell` 그리드 트랙-카운팅 방식을 flex column으로 전환해 밴드 개수 변경에 견고하게 만든다.

**Tech Stack:** Flask(Jinja 템플릿) + 정적 HTML/CSS/Vanilla JS. 개발 서버: `python web_app/app.py` (기본 포트 5000).

---

## 검증 방식 안내 (이 계획의 "테스트")

이 저장소에는 프론트엔드 자동 테스트 러너가 없다. 각 태스크의 검증은 **(a) 개발 서버 기동 후 페이지 로드 + (b) 스모크 체크(템플릿 렌더 200 + 핵심 ID 존재) + (c) 브라우저 육안 확인**으로 한다. 커밋은 태스크마다 수행한다.

**개발 서버 기동 (한 번만, 백그라운드):**
```
python web_app/app.py
```
이미 떠 있으면 재기동 불필요. 정적 파일(`scanner.css`, `scanner.html`)은 즉시 반영되므로 브라우저 새로고침(Ctrl+Shift+R)만 하면 된다.

**재사용 스모크 체크 (PowerShell):**
```powershell
$r = Invoke-WebRequest -UseBasicParsing http://localhost:5000/
$ids = 'view-tabs','stat-total','stat-strong','stat-sector','macro-signal','macro-items','macro-meta','macro-events-strip','macro-events-strip-list','filter-chips','score-eval-stat'
$missing = $ids | Where-Object { $r.Content -notmatch [regex]::Escape($_) }
if ($missing) { "MISSING: $($missing -join ', ')" } else { "OK: 모든 핵심 ID 존재 / status $($r.StatusCode)" }
```
기대 출력: `OK: 모든 핵심 ID 존재 / status 200`

---

## File Structure

| 파일 | 역할 | 변경 |
|------|------|------|
| `web_app/templates/scanner.html` | 상단 밴드 마크업 | ②③④⑤⑥ 띠 DOM을 탭바·컨텍스트바·필터바로 재배치 |
| `web_app/static/scanner.css` | 레이아웃·스타일 | app-shell flex 전환, 신규 밴드 스타일, 구 스타일 정리 |
| `web_app/static/app.js` | 동작 | **변경 없음** (보존 계약만 유지) |

**보존 계약 (절대 깨지면 안 되는 ID/속성):**
`#mobile-menu-btn`, `#market-btn-group`, `#search-input`, `#btn-scan`, `#topbar-date`, `.view-tab[data-view][data-action]`, `#stat-total`, `#stat-strong`, `#stat-sector`, `#score-eval-stat`, `#score-eval-badge`, `#macro-strip`, `#macro-signal`, `#macro-leading`, `#macro-items`, `#macro-meta`, `#macro-events-strip`(+`.empty` 토글 동작), `#macro-events-strip-list`, `#filter-chips`(+칩 `data-filter`).

---

## Task 1: `.app-shell`을 flex column으로 전환

밴드 개수에 의존하는 그리드 트랙 계산을 제거해, 이후 밴드 재배치가 레이아웃을 깨지 않도록 기반을 만든다. 이 단계만으로는 화면이 거의 동일하게 보여야 한다.

**Files:**
- Modify: `web_app/static/scanner.css:15-23` (`.app-shell`)
- Modify: `web_app/static/scanner.css:496-500` (`.content`)
- Modify: `web_app/static/scanner.css:3328-3335` (모바일 `.app-shell`)

- [ ] **Step 1: `.app-shell` 규칙 교체**

`scanner.css` 15-23번 줄을 아래로 교체:
```css
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  max-width: 100vw;
}
```

- [ ] **Step 2: `.content`가 남은 공간을 채우도록 수정**

`scanner.css` 496-500번 줄의 `.content` 규칙을 아래로 교체(기존 grid 컬럼 유지 + flex 채움 추가):
```css
.content {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px 1fr;
  overflow: hidden;
}
```

- [ ] **Step 3: 모바일 `.app-shell`에서 grid-template-rows 제거**

`scanner.css` 3328-3335 영역의 모바일 `.app-shell` 규칙에서 `grid-template-rows: 52px auto auto auto 1fr;` 줄을 삭제(나머지 height/overflow 유지):
```css
@media (max-width: 768px) {
  .app-shell {
    height: 100dvh;
    height: 100vh; /* fallback */
    max-width: 100vw;
    overflow-x: hidden;
  }
```

- [ ] **Step 4: 검증 — 서버 로드 + 스모크 체크**

서버가 떠 있는지 확인 후 위 "재사용 스모크 체크" 실행.
기대: `OK: 모든 핵심 ID 존재 / status 200`.
브라우저에서 http://localhost:5000/ 새로고침 → 상단 밴드 순서·콘텐츠 영역이 기존과 동일하게 보이고 하단 빈 공간 없이 콘텐츠가 채워지는지 확인.

- [ ] **Step 5: Commit**

```bash
git add web_app/static/scanner.css
git commit -m "refactor(layout): app-shell을 flex column으로 전환 (그리드 트랙 의존 제거)"
```

---

## Task 2: HTML 재배치 — 탭+Stats / 컨텍스트 바 / 필터칩

`scanner.html`의 ②매크로이벤트·③면책·④매크로스트립·⑤뷰탭·⑥Stats Bar 마크업을 새 3블록으로 재배치한다. 모든 보존 계약 ID/속성을 그대로 옮긴다.

**Files:**
- Modify: `web_app/templates/scanner.html:76-133` (밴드 ②~⑥ 전체)

- [ ] **Step 1: 76-133번 줄(매크로이벤트~Stats Bar)을 아래 마크업으로 교체**

```html
  <!-- Scanner Tab Bar: 큰 세그먼트 탭 + 인라인 Stats -->
  <div class="scanner-tabbar">
    <div class="view-tabs" role="tablist" aria-label="화면 전환">
      <button class="view-tab active" data-view="stock" data-action="showStockView">📈 종목 스캐너</button>
      <button class="view-tab" data-view="etf" data-action="openEtfView" title="미국·한국 인기 ETF를 한눈에 — 구성종목·섹터·수수료·수익률">📊 ETF 현황</button>
    </div>
    <div class="tabbar-stats">
      <div class="stat-item">
        <span class="stat-label">스캔 종목</span>
        <span id="stat-total" class="stat-value">—<span class="unit">개</span></span>
      </div>
      <div class="stat-item">
        <span class="stat-label" title="종합점수 75점 이상 S등급 — 알고리즘 스크리닝 결과임">S등급</span>
        <span id="stat-strong" class="stat-value">—<span class="unit">개</span></span>
      </div>
      <div class="stat-item">
        <span class="stat-label">섹터</span>
        <span id="stat-sector" class="stat-value" style="font-size:13px;font-weight:500;">전체</span>
      </div>
      <div class="stat-item" id="score-eval-stat" hidden>
        <span class="stat-label" title="점수가 미래 수익을 실제로 예측하는지 표본외(out-of-sample) 검증한 결과. IC(정보계수)>0이면 고점수가 실제로 더 올랐다는 뜻. 스냅샷이 쌓일수록 신뢰도 상승.">점수 신뢰도</span>
        <span id="score-eval-badge" class="score-eval-badge none">—</span>
      </div>
    </div>
  </div>

  <!-- Context Bar: 신호등 + 지수 + 매크로 이벤트 + 축약 면책 (구 ②③④ 통합) -->
  <div class="context-bar" id="macro-strip">
    <span class="macro-signal unknown" id="macro-signal">⚪ <span>로딩…</span></span>
    <span class="macro-leading hidden" id="macro-leading"></span>
    <div id="macro-items" style="display:flex;align-items:center;gap:14px;"></div>
    <span id="macro-events-strip" class="macro-events-strip empty">
      <span class="macro-events-strip-label">📅 매크로</span>
      <span id="macro-events-strip-list" style="display:inline-flex;gap:6px;"></span>
    </span>
    <span class="macro-meta" id="macro-meta"></span>
    <span class="ctx-disclaimer" role="note" title="여기 나오는 점수·등급·신호는 알고리즘 스크리닝 결과일 뿐임. 판단과 손익은 본인 책임임.">⚠️ 알고리즘 스크리닝 · 투자 본인책임</span>
  </div>

  <!-- Filter Bar: 빠른 필터 칩 (구 Stats Bar 내부에서 분리) -->
  <div class="filter-bar">
    <div id="filter-chips" class="filter-chips">
      <button class="chip active" data-filter="all">전체</button>
      <button class="chip" data-filter="watchlist" title="내가 추가한 관심종목만 표시">💎 관심종목</button>
      <button class="chip" data-filter="strong" title="종합점수 60점 이상 — S등급(75+)·A등급(60+) 해당 종목만 표시">🔥 S·A등급</button>
      <button class="chip" data-filter="entry_green" title="타점점수 70점 이상 — 기술 신호가 모두 양호한 종목">🟢 기회 탐색</button>
      <button class="chip chip-delta" data-filter="score_surge" title="어제 대비 종합점수 +3 이상 급등">📈 점수급등</button>
      <button class="chip chip-delta" data-filter="new_entry" title="기준일 이후 목록에 새로 진입한 종목">🆕 신규진입</button>
      <button class="chip" data-filter="breakout" title="추세 돌파 감지 종목">🚀 돌파</button>
      <button class="chip" data-filter="bf_buy" title="저점매수 점수 25점 이상 — 과매도+재무건전 후보 (40+: 적극, 60+: 강력)">🎣 저점매수</button>
      <button class="chip" data-filter="laggard" title="RS Rating 40 미만 또는 위험 등급 — 주의 대상">⛔ 위험</button>
    </div>
  </div>
```

> 주의: 교체 후 바로 아래 `<!-- 지수별 보기 -->` (`#index-bar`) 블록은 그대로 둔다. `#macro-strip`의 자식 ID(`macro-signal`/`macro-leading`/`macro-items`/`macro-meta`)와 `#macro-events-strip`/`#macro-events-strip-list`, `.empty` 클래스가 모두 보존되어야 JS가 동작한다.

- [ ] **Step 2: 검증 — 스모크 체크로 모든 ID 보존 확인**

위 "재사용 스모크 체크" 실행.
기대: `OK: 모든 핵심 ID 존재 / status 200`. (하나라도 MISSING이면 Step 1 마크업에서 누락 ID 복구)

- [ ] **Step 3: 검증 — 동작 확인(육안)**

브라우저 새로고침 후:
- `종목 스캐너` ↔ `ETF 현황` 탭 클릭 전환이 동작하는지
- 스캔 실행 시 스캔 종목/S등급/섹터 숫자가 채워지는지
- 필터칩 클릭이 동작하는지
- 콘솔(F12) 에러 없는지
이 시점엔 스타일이 아직 안 입혀져 배치가 어색할 수 있음(정상). 다음 태스크에서 스타일 적용.

- [ ] **Step 4: Commit**

```bash
git add web_app/templates/scanner.html
git commit -m "refactor(scanner): 상단 밴드 DOM을 탭바·컨텍스트바·필터바로 재배치"
```

---

## Task 3: CSS — 탭바(큰 세그먼트 탭 + 인라인 Stats)

**Files:**
- Modify: `web_app/static/scanner.css:3804-3835` (`.view-tabs`/`.view-tab`)

- [ ] **Step 1: 탭바 컨테이너 + 큰 세그먼트 탭 + 인라인 stats 스타일 추가/교체**

`scanner.css` 3804-3835 영역의 `.view-tabs` 관련 규칙을 아래로 교체:
```css
/* ── Scanner Tab Bar (탭 + 인라인 Stats) ───────────────────── */
.scanner-tabbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 24px;
  background: var(--surface-page);
}
.scanner-tabbar .tabbar-stats {
  display: flex;
  align-items: center;
  margin-left: auto;
}
.tabbar-stats .stat-item {
  padding: 0 14px;
  margin: 0;
  border-right: 1px solid var(--border);
}
.tabbar-stats .stat-item:last-child { border-right: none; padding-right: 0; }
.tabbar-stats .stat-label { font-size: 11px; }
.tabbar-stats .stat-value { font-size: 14px; }

/* 큰 세그먼트 탭 (종목 스캐너 / ETF 현황) */
.view-tabs {
  display: flex;
  gap: 2px;
  align-items: center;
  width: fit-content;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 3px;
  margin: 0;
}
.view-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  transition: background .15s, color .15s;
}
.view-tab:hover { color: var(--text-primary); }
.view-tab.active {
  background: var(--brand);
  color: var(--primary-foreground);
  box-shadow: 0 2px 8px rgba(0, 113, 227, 0.3);
}
```

- [ ] **Step 2: 검증**

브라우저 새로고침 → 탭바 한 줄에 왼쪽 큰 세그먼트 탭(활성 탭 brand색 채움), 오른쪽 끝에 스캔/S등급/섹터 인라인 stats가 보이는지 확인. 스모크 체크 `OK` 유지.

- [ ] **Step 3: Commit**

```bash
git add web_app/static/scanner.css
git commit -m "style(scanner): 큰 세그먼트 탭 + 인라인 Stats 탭바 스타일"
```

---

## Task 4: CSS — 통합 컨텍스트 바 + 축약 면책

기존 `.macro-strip` 컨테이너 규칙을 `.context-bar`로 대체하고, 내부에 들어온 매크로 이벤트(`#macro-events-strip`)를 인라인으로 재스타일, 축약 면책(`.ctx-disclaimer`)을 추가한다. 자식 요소 셀렉터(`.macro-signal`, `.macro-item`, `.macro-leading`, `.macro-meta`, `.macro-sep`)는 그대로 유지된다.

**Files:**
- Modify: `web_app/static/scanner.css:42-56` (`.macro-strip` 컨테이너 규칙)
- Modify: `web_app/static/scanner.css:100-107` (`.macro-meta` — 그대로 두되 확인)

- [ ] **Step 1: `.macro-strip` 컨테이너 규칙(42-57)을 `.context-bar`로 교체**

`scanner.css`에서 `.macro-strip { ... }` 와 `.macro-strip::-webkit-scrollbar { display: none; }` (42-57번 줄)을 아래로 교체. **(`.macro-signal` 이하 자식 규칙 58번 줄부터는 건드리지 않는다.)**
```css
/* ── Context Bar (신호등 + 지수 + 매크로 이벤트 + 축약 면책) ── */
.context-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 24px;
  height: 36px;
  background: var(--card);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
  white-space: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  z-index: 90;
}
.context-bar::-webkit-scrollbar { display: none; }
/* 컨텍스트 바 안으로 들어온 매크로 이벤트 — 밴드 스타일 해제하고 인라인화 */
.context-bar .macro-events-strip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  background: none;
  border: none;
  overflow: visible;
}
.context-bar .macro-events-strip.empty { display: none; }
.context-bar .macro-meta { margin-left: auto; }
/* 축약 면책 고지 (항상 노출, 전체 문구는 title 툴팁) */
.ctx-disclaimer {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #C77700;
  white-space: nowrap;
  cursor: help;
  flex: none;
}
```

- [ ] **Step 2: 검증**

브라우저 새로고침 → 탭바 아래 한 줄에 `🟢 신호등 + 지수 + (이벤트칩) + 신선도 meta + ⚠️ 축약 면책`이 한 줄로 보이고, 좁으면 가로 스크롤되는지 확인. 매크로 데이터 로드 후 신호등/지수 채워지는지, 이벤트 없을 때 📅 영역이 숨는지 확인.

- [ ] **Step 3: Commit**

```bash
git add web_app/static/scanner.css
git commit -m "style(scanner): 매크로·이벤트·면책을 단일 컨텍스트 바로 통합"
```

---

## Task 5: CSS — 필터칩 줄 + 구(舊) 스타일 정리

**Files:**
- Modify: `web_app/static/scanner.css:343-372` (`.stats-bar`/`.stat-item` 관련)
- Modify: `web_app/static/scanner.css:25-40` (`.disclaimer-band` — 사용처 제거됨)
- Modify: `web_app/static/scanner.css:3320-3321` (반응형 `.stats-bar` 잔재)

- [ ] **Step 1: 필터바 스타일 추가**

`scanner.css`의 `.filter-chips { ... }` 규칙(375번 줄) 바로 앞에 추가:
```css
/* ── Filter Bar (빠른 필터 칩 줄) ──────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  padding: 8px 24px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
}
```

- [ ] **Step 2: 구 `.stats-bar` 컨테이너 규칙 삭제**

`scanner.css` 343-351번 줄의 `.stats-bar { ... }` 규칙을 **삭제**한다. (`.stat-item`/`.stat-label`/`.stat-value`/`.stat-value .unit` 규칙 353-372는 탭바 인라인 stats에서 계속 사용하므로 **남긴다.**)

- [ ] **Step 3: 구 `.disclaimer-band` 규칙 삭제(사용처 없음)**

`scanner.css` 25-40번 줄의 `.disclaimer-band` 관련 규칙(데스크탑 + `@media` 블록 포함)을 **삭제**한다. 마크업에서 이미 제거되어 죽은 코드다.

- [ ] **Step 4: 반응형 `.stats-bar` 잔재 정리**

`scanner.css` 3320번 줄 `.stats-bar { padding: 0 16px; }` 를 삭제한다. (모바일 세부 조정은 Task 6에서 새로 정의)

- [ ] **Step 5: 검증**

스모크 체크 `OK` 유지. 브라우저 새로고침 → 필터칩이 컨텍스트 바 아래 자체 줄로 정상 표시·클릭 동작. 콘솔 에러 없음.

- [ ] **Step 6: Commit**

```bash
git add web_app/static/scanner.css
git commit -m "style(scanner): 필터칩 줄 분리 + 구 stats-bar·disclaimer 죽은 스타일 정리"
```

---

## Task 6: 반응형(모바일 ≤768px) 조정

**Files:**
- Modify: `web_app/static/scanner.css:3373-3381` (모바일 `.stats-bar`/`.stat-*`)
- Modify: `web_app/static/scanner.css:3832-3835` (기존 모바일 `.view-tabs`/`.view-tab` — 있으면 교체)

- [ ] **Step 1: 모바일 `.stats-bar` 규칙(3373-3381)을 새 밴드용으로 교체**

해당 블록을 아래로 교체:
```css
  .scanner-tabbar {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    padding: 8px 12px;
  }
  .view-tab { flex: 1; justify-content: center; padding: 7px 0; font-size: 13px; }
  .tabbar-stats { margin-left: 0; justify-content: flex-start; }
  .tabbar-stats .stat-item { padding: 0 10px 0 0; border-right: none; }
  .tabbar-stats .stat-value { font-size: 13px; }
  .context-bar { padding: 0 12px; height: 34px; }
  .ctx-disclaimer { font-size: 10px; }
  .filter-bar { padding: 6px 12px; }
```

> 이 규칙들은 기존 `@media (max-width: 768px)` 블록(3328~) 내부에 위치해야 한다. 교체 대상이 그 블록 안의 `.stats-bar`/`.stat-item`/`.stat-label`/`.stat-value` 줄임을 확인하고 통째로 대체한다.

- [ ] **Step 2: 모바일 구 `.view-tabs`/`.view-tab` 잔재 제거**

`scanner.css` 3832-3835 부근에 남은 구 모바일 규칙
```css
@media (max-width: 768px) {
  .view-tabs { margin: 8px 10px 0; }
  .view-tab { padding: 6px 14px; font-size: 12.5px; }
}
```
이 있으면 **삭제**한다(Step 1에서 새로 정의했으므로 중복·충돌 방지).

- [ ] **Step 3: 검증 — 모바일 폭**

브라우저 DevTools 디바이스 모드(폭 ~390px) 또는 창을 좁혀:
- 탭이 가로 꽉 채워 2등분되는지
- Stats가 탭 아래 한 줄로 내려오는지
- 컨텍스트 바가 가로 스크롤되며 넘침 없는지
- 가로 스크롤바(전체 페이지)가 생기지 않는지
확인.

- [ ] **Step 4: Commit**

```bash
git add web_app/static/scanner.css
git commit -m "style(scanner): 재구성 헤더 모바일 반응형 조정"
```

---

## Task 7: 최종 검증 + 죽은 코드 스윕

**Files:**
- Inspect: `web_app/static/scanner.css`, `web_app/templates/scanner.html`

- [ ] **Step 1: 죽은 셀렉터 잔재 검색**

```powershell
Select-String -Path web_app/static/scanner.css -Pattern '\.macro-strip\b','\.disclaimer-band\b','\.stats-bar\b','\.view-tabs\s*\{' |
  Select-Object LineNumber, Line
```
기대: `.macro-strip`(컨테이너), `.disclaimer-band`, `.stats-bar` 컨테이너 규칙이 더 이상 없어야 한다. (자식 `.macro-signal`/`.macro-item` 등은 남아 있어도 정상.) 남아 있으면 해당 줄 제거.

- [ ] **Step 2: 전체 스모크 체크 + 데스크탑 육안 확인**

스모크 체크 `OK: 모든 핵심 ID 존재 / status 200` 확인. 데스크탑에서:
1. 상단이 **TopBar / 탭+Stats / 컨텍스트 바 / 필터칩** 4줄로 정리되고 기존 6띠보다 세로가 줄었다
2. `종목 스캐너` 탭이 brand색 대형 세그먼트로 또렷하다
3. 종목↔ETF 전환 동작
4. 스캔 후 stats 숫자 채워짐, 매크로 신호등·지수·이벤트 표시, 필터칩 동작
5. 면책이 컨텍스트 바에 항상 노출(hover 시 전체 문구 툴팁)
6. 콘솔 에러 없음

- [ ] **Step 3: 수용 기준 대조**

스펙 8절 수용 기준 1~7을 하나씩 대조 확인.

- [ ] **Step 4: 최종 Commit (잔재 제거가 있었던 경우)**

```bash
git add web_app/static/scanner.css
git commit -m "chore(scanner): 헤더 재구성 죽은 스타일 최종 정리"
```

---

## Self-Review 결과

- **스펙 커버리지:** 3-1 TopBar(무변경, Task 2에서 유지) · 3-2 탭+Stats(Task 2 HTML + Task 3 CSS) · 3-3 컨텍스트 바(Task 2 + Task 4) · 3-4 필터칩(Task 2 + Task 5) · 4-2 그리드(Task 1) · 5 반응형(Task 6) · 6 빈 상태(보존 계약 + Task 4 `.empty`) · 8 수용 기준(Task 7) — 전부 매핑됨.
- **플레이스홀더:** 없음(모든 코드 블록 구체화).
- **타입/이름 일관성:** `.scanner-tabbar`/`.tabbar-stats`/`.context-bar`/`.ctx-disclaimer`/`.filter-bar`/`.macro-events-strip` 클래스명이 HTML(Task 2)과 CSS(Task 3~6)에서 일치. 보존 ID 목록과 Task 2 마크업 일치.
