# 종목 스캐너 상단 헤더 재구성 — 설계 문서

**작성일:** 2026-06-10
**대상:** `web_app/templates/scanner.html`, `web_app/static/scanner.css` (필요 시 `web_app/static/app.js` 소폭)
**방향:** B · 세그먼트 강조형

## 1. 배경 / 문제

현재 상단 영역은 6개의 가로 띠(band)가 세로로 쌓여 콘텐츠 시작 전 세로 공간을 많이 차지한다. 동시에 "종목 스캐너"라는 앱 정체성이 작은 뷰 탭 글자로만 표시돼 잘 보이지 않는다.

현재 띠 구성 (위 → 아래):

1. **TopBar** — 로고 `(.)(.) 분석기` · 미국/한국 토글 · 검색 · 스캔 · 오버플로(⋯) · 날짜
2. **매크로 이벤트 스트립** (`#macro-events-strip`) — 📅 이벤트 칩, 비어 있으면 `.empty`로 숨김
3. **면책 고지 밴드** (`.disclaimer-band`) — ⚠️ 알고리즘 결과·본인 책임
4. **매크로 스트립** (`#macro-strip`) — 🟢 신호등 + 지수(S&P/VIX/10Y 등) + 신선도 meta
5. **뷰 탭** (`.view-tabs`) — `📈 종목 스캐너` / `📊 ETF 현황`
6. **Stats Bar** (`.stats-bar`) — 스캔 종목·S등급·섹터·(조건부)점수 신뢰도 + **필터칩**(전체/관심종목/S·A등급/...)

## 2. 목표

- 세로 공간을 알차게: 6개 띠 → **3줄 + 필터칩 줄**로 압축.
- "종목 스캐너" 정체성을 **크고 또렷한 세그먼트 탭**으로 승격.
- 기존 동작·ID·이벤트 핸들러를 최대한 보존(JS 변경 최소, 주로 HTML 재배치 + CSS).

## 3. 목표 구조 (위 → 아래)

### 3-1. TopBar (구조 변경 없음)
로고 · 미국/한국 토글 · 검색 박스 · 스캔 버튼 · 오버플로 메뉴 · 날짜. 기존 마크업 유지.

### 3-2. 탭 + Stats 줄 (신규 통합 — 기존 ⑤ 뷰탭 + ⑥의 stat 항목)
- **왼쪽:** 큰 세그먼트 탭
  - `📈 종목 스캐너` / `📊 ETF 현황`
  - 활성 탭: brand색(`var(--brand)`, 라이트 `#0071E3`) 배경 채움 + 흰 글자 + 그림자, 폰트 14px / weight 800, 패딩 8px 18px.
  - 비활성 탭: `var(--text-secondary)`.
  - **`.view-tab` 클래스 · `data-view` · `data-action`(showStockView / openEtfView) 속성을 그대로 유지** → `_setViewTab()` 및 기존 토글 로직이 변경 없이 동작.
- **오른쪽(인라인 Stats):** 스캔 종목(`#stat-total`) · S등급(`#stat-strong`) · 섹터(`#stat-sector`) — 항목 사이 세로 구분선(`.sep`). 점수 신뢰도(`#score-eval-stat` / `#score-eval-badge`)는 기존처럼 **조건부(있을 때만) 표시**.
- 정렬: 탭은 왼쪽, Stats는 `margin-left:auto`로 오른쪽 끝.

### 3-3. 컨텍스트 바 (기존 ②③④ 통합 — 한 줄)
좌 → 우 순서로 한 줄에 통합, 가로 스크롤(`overflow-x:auto`, 스크롤바 숨김):
- `🟢 안정` 신호등 (`#macro-signal`, 기존 클래스 stable/caution/danger/unknown 유지)
- `#macro-leading` (조건부)
- 지수 항목들 (`#macro-items`) — S&P / VIX / 10Y 등
- 매크로 이벤트 칩 (`#macro-events-strip-list`) — 📅 D-2 CPI 형식. 이벤트 없으면 칩 영역 숨김.
- (우측) 축약 면책: `⚠️ 알고리즘 스크리닝 · 투자 본인책임` — 작은 글씨(`#C77700` 톤), 항상 노출. 전체 문구는 `title` 툴팁로 제공.
- (우측) 신선도 meta (`#macro-meta`).

### 3-4. 필터칩 줄 (기존 유지, 위치만 정리)
기존 Stats Bar 마지막 flex 항목에 들어있던 `#filter-chips`(전체/💎관심종목/🔥S·A등급/🟢기회탐색/📈점수급등/🆕신규진입/🚀돌파/🎣저점매수/⛔위험)를 **자체 줄(band)로 분리**해 유지. 칩 마크업·`data-filter`·기존 동작 변경 없음.

## 4. 변경 대상 / 보존 계약

### 4-1. HTML (`scanner.html`)
- ②③④⑤⑥ 띠의 DOM을 재배치: 뷰 탭 + stat 항목을 한 줄 컨테이너로, ②③④를 한 줄 컨텍스트 바 컨테이너로, 필터칩을 자체 줄로.
- **반드시 보존할 ID/속성:** `#mobile-menu-btn`, `#market-btn-group`, `#search-input`, `#btn-scan`, `#topbar-date`, `#macro-events-strip`(+`#macro-events-strip-list`), `#macro-strip`(+`#macro-signal`, `#macro-leading`, `#macro-items`, `#macro-meta`), `.view-tab[data-view][data-action]`, `#stat-total`, `#stat-strong`, `#stat-sector`, `#score-eval-stat`, `#score-eval-badge`, `#filter-chips`(+칩 `data-filter`).
- 면책 문구 element는 유지하되 컨텍스트 바 안의 축약 형태로 이동.

### 4-2. CSS (`scanner.css`)
- `.app-shell { grid-template-rows: ... }` 재정의: 새 band 구성(topbar / 탭+stats / 컨텍스트 바 / 필터칩 / index-bar / content)에 맞춰 행 수·높이 조정. 마지막 content만 `1fr`.
- 신규/수정 클래스: 큰 세그먼트 탭(`.view-tabs`, `.view-tab`, `.view-tab.active` 확대), 탭 줄 인라인 stats 레이아웃, 통합 컨텍스트 바, 축약 면책 인라인, 필터칩 줄.
- 기존 `.macro-strip`, `.macro-events-strip`, `.stats-bar`, `.disclaimer-band` 규칙은 새 구조에 맞게 통합·정리.

### 4-3. JS (`app.js`)
- 원칙적으로 변경 없음. `_setViewTab()`, `showStockView()`, `openEtfView()`, 매크로/이벤트 렌더링은 기존 ID를 그대로 참조하므로 보존 계약만 지키면 동작.
- DOM 위치 이동으로 셀렉터가 깨지지 않는지만 점검(모든 참조가 `getElementById`/클래스 기반이므로 위치 무관).

## 5. 반응형 (모바일, ≤768px)
- 탭: 가로 폭을 꽉 채워 2등분(각 `flex:1`, 중앙 정렬, 폰트 약간 축소).
- Stats: 탭 줄에서 분리해 탭 아래 한 줄로 배치.
- 컨텍스트 바: 가로 스크롤.
- 면책: 더 작은 글씨로 한 줄(필요 시 ⚠️ⓘ 아이콘 + 툴팁).
- 기존 `#mobile-menu-btn`(☰) 동작 유지.

## 6. 빈 상태 / 조건부 표시
- 매크로 이벤트 없음 → 이벤트 칩 영역 숨김(`.empty`/JS 기존 로직).
- 점수 신뢰도 데이터 없음 → `#score-eval-stat` 숨김(기존 `hidden`).
- 신호등 로딩 중 → `unknown` 상태(⚪) 표시.

## 7. 범위 밖 (이번에 건드리지 않음)
- `#index-bar`(지수별 보기), `#sector-concentration-banner`, 종목 테이블(`.stock-table`), ETF 뷰 내부, 사이드바.
- 새 기능 추가 없음 — 순수 레이아웃/시각 재구성.

## 8. 수용 기준 (Acceptance)
1. 상단이 **TopBar / 탭+Stats / 컨텍스트 바 / 필터칩**의 4개 줄로 정리되고, 기존 6띠 대비 세로 공간이 눈에 띄게 줄어든다.
2. `종목 스캐너` 탭이 brand색으로 채워진 큰 세그먼트로 또렷하게 보인다.
3. 종목 스캐너 ↔ ETF 현황 전환이 기존과 동일하게 동작한다.
4. 스캔 종목·S등급·섹터 수치, 매크로 신호등·지수·이벤트, 필터칩이 모두 정상 표시·동작한다.
5. 면책 문구가 항상(축약 형태로) 노출된다.
6. 모바일에서 가로 넘침 없이 탭/Stats/컨텍스트 바가 정리되어 보인다.
7. 콘솔 에러 없음, 기존 JS 핸들러 정상 바인딩.
