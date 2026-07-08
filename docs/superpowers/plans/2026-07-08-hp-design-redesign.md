# 종목스캐너 HP 디자인 언어 리디자인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `web_app`의 애플 디자인 언어(theme.css/scanner.css)를 HP 디자인 언어 기반으로 전면 교체한다 — 단일 블루 액센트(`#024ad8`), "버튼은 날카롭게·카드는 부드럽게" 2단 radius, 색 대비 기반 elevation, 캔버스/클라우드/포그 밴드 리듬을 4개 페이지(scanner/detail/compare/pyramid)에 적용한다.

**Architecture:** 대부분의 컴포넌트가 이미 `var(--brand)`, `var(--card)`, `var(--radius)`, `var(--shadow-card)` 같은 CSS 커스텀 프로퍼티를 통해 `theme.css`를 참조하므로, **Task 1(theme.css 토큰 재정의)이 가장 큰 레버리지를 갖는다** — 이 한 번의 수정으로 버튼·카드·텍스트·보더 색 대부분이 자동으로 새 톤을 반영한다. 이후 태스크는 토큰만으로 커버되지 않는 하드코딩된 값(개별 px radius, 하드코딩 hex 색상, 페이지별 인라인 `<style>`)을 선택자 단위로 찾아 교체한다.

**Tech Stack:** 순수 CSS 커스텀 프로퍼티(변수), Jinja2 템플릿(`web_app/templates/*.html`), Flask 개발 서버, Playwright(시각 검증용, 이미 `web_app/_browser_e2e.py`에서 사용 중).

## Global Constraints

- 다크모드(`.dark` 클래스, theme.css:99-143)는 범위 밖 — 어떤 태스크도 `.dark` 블록을 수정하지 않는다.
- 색상값은 스펙 문서(`docs/superpowers/specs/2026-07-08-hp-design-redesign-design.md`)의 표에 명시된 값을 그대로 사용한다 — 임의 변형 금지.
- `--warning`, `--info`, `--chart-1`~`--chart-5` 토큰은 스펙에 명시되지 않았으므로 이번 작업 범위에서 값을 바꾸지 않는다.
- 등급 S 색상(`#7C3AED`)은 스펙에 따라 유지 — 변경하지 않는다.
- 모든 CSS 수정 후에는 반드시 로컬 서버(`python web_app/app.py`, 기본 포트 5000)를 띄워 대상 페이지가 깨지지 않았는지 브라우저 또는 `curl`로 확인한다.

---

## File Structure

이번 작업은 새 파일을 만들지 않고 기존 4개 파일만 수정한다.

- `web_app/static/theme.css` — 전역 디자인 토큰(색상/radius/shadow). Task 1에서 전면 재정의.
- `web_app/static/scanner.css` — `scanner.html`(메인)과 `detail.html`이 공유하는 컴포넌트 스타일(5979줄). Task 2~5에서 선택자 그룹 단위로 수정.
- `web_app/templates/detail.html` — 자체 인라인 `<style>`(12~1098줄) 보유. Task 6에서 하드코딩된 radius/shadow 일부만 수정(대부분은 Task 1 토큰 재정의로 자동 반영됨).
- `web_app/templates/compare.html` — 자체 인라인 `<style>`(8~173줄, 166줄로 소규모). Task 7에서 전체 검토.
- `web_app/templates/pyramid.html` — 자체 인라인 `<style>`(8~145줄, 138줄로 소규모). Task 8에서 전체 검토 — `var(--accent)`를 솔리드 버튼 배경으로 잘못 쓰고 있는 기존 버그도 함께 수정.

---

### Task 1: theme.css 전역 토큰 재정의

**Files:**
- Modify: `web_app/static/theme.css:4-83` (`:root` 블록만 — `.dark` 블록(99-143)과 `:focus-visible` 규칙(85-97)은 건드리지 않음)

**Interfaces:**
- Consumes: 없음(최초 태스크)
- Produces: 아래 CSS 커스텀 프로퍼티. 이후 모든 태스크는 이 이름들을 그대로 참조한다.
  - `--brand: #024ad8`, `--brand-pressed: #0e3191`, `--brand-soft: #c9e0fc`
  - `--radius-sharp: 4px`, `--radius-pill: 9999px`, `--radius-badge: 8px` (신규)
  - `--radius: 16px` (기존 18px에서 변경 — "카드" 역할 유지)
  - `--stock-up`, `--stock-down`은 별도 토큰을 신설하지 않고 기존 `--success`/`--destructive`를 재정의해 대체한다(scanner.css에 이미 `var(--success)`/`var(--destructive)`가 54곳에서 상승/하락 표시에 쓰이고 있으므로, 신규 토큰 추가보다 기존 토큰 값 교체가 더 적은 변경으로 전체를 커버함)

- [ ] **Step 1: 현재 `:root` 블록 백업 확인 (git diff 기준점)**

Run: `git -C "web_app/.." diff --stat` (또는 저장소 루트에서 `git status`)
Expected: `web_app/static/theme.css`가 아직 변경 목록에 없음(수정 전 상태 확인용)

- [ ] **Step 2: `:root` 블록을 HP 토큰으로 교체**

`web_app/static/theme.css`의 4~83번 줄(`:root {` 부터 여는 줄 다음의 첫 `}` 까지)을 아래로 교체한다:

```css
:root {
  /* Brand — HP Electric Blue */
  --brand: #024ad8;
  --brand-pressed: #0e3191;
  --brand-soft: #c9e0fc;
  --primary: #1a1a1a;
  --primary-foreground: #ffffff;

  /* Surface */
  --background: #ffffff;
  --foreground: #1a1a1a;
  --card: #ffffff;
  --card-foreground: #1a1a1a;
  --popover: #ffffff;
  --popover-foreground: #1a1a1a;

  /* Secondary / Muted — HP cloud/fog bands */
  --secondary: #f7f7f7;
  --secondary-foreground: #1a1a1a;
  --muted: #e8e8e8;
  --muted-foreground: #636363;
  --accent: #c9e0fc;
  --accent-foreground: #024ad8;

  /* Semantic Status */
  --destructive: #b3262b;
  --destructive-foreground: #ffffff;
  --success: #0f8a5f;
  --success-foreground: #ffffff;
  --warning: #FF9500;
  --warning-foreground: #ffffff;
  --info: #007AFF;
  --info-foreground: #ffffff;

  /* Text Hierarchy */
  --text-primary: #1a1a1a;
  --text-secondary: #3d3d3d;
  --text-tertiary: #636363;
  --text-disabled: #929292;
  --icon-default: #3d3d3d;

  /* Page Surfaces */
  --surface-page: #ffffff;
  --surface-subtle: #f7f7f7;
  --surface-muted: #e8e8e8;
  --brand-tint: #c9e0fc;
  --alert-badge: #b3262b;

  /* Border / Input — HP hairline default */
  --border: #e8e8e8;
  --input: transparent;
  --input-background: #f7f7f7;
  --switch-background: #929292;
  --ring: rgba(2, 74, 216, 0.4);

  /* Radius — HP 2-tier: sharp buttons, soft cards */
  --radius: 16px;
  --radius-sharp: 4px;
  --radius-pill: 9999px;
  --radius-badge: 8px;

  /* Shadows — HP flat + color-contrast depth */
  --shadow-card:     0 2px 8px rgba(26, 26, 26, 0.08);
  --shadow-button:   none;
  --shadow-hover:    0 2px 8px rgba(26, 26, 26, 0.08);
  --shadow-elevated: 0 8px 24px rgba(26, 26, 26, 0.12);
  --shadow-modal:    0 8px 24px rgba(26, 26, 26, 0.12);

  /* Animation — unchanged */
  --duration-fast:     100ms;
  --duration-normal:   200ms;
  --duration-moderate: 300ms;
  --duration-slow:     400ms;
  --ease-default: cubic-bezier(0.25, 0.1, 0.25, 1);
  --ease-in:      cubic-bezier(0.42, 0, 1, 1);
  --ease-out:     cubic-bezier(0, 0, 0.58, 1);
  --ease-spring:  cubic-bezier(0.34, 1.56, 0.64, 1);

  /* Charts — unchanged, out of scope */
  --chart-1: #0071E3;
  --chart-2: #34C759;
  --chart-3: #FF3B30;
  --chart-4: #FF9500;
  --chart-5: #86868B;
}
```

- [ ] **Step 3: 서버 기동 후 메인 페이지가 깨지지 않는지 확인**

Run:
```bash
cd web_app && PORT=5050 python app.py &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/
```
Expected: `200` 출력 (CSS 파싱 에러로 페이지 자체가 깨지는 경우가 아님을 확인하는 최소 스모크 테스트)

- [ ] **Step 4: 브랜드 색상이 실제로 바뀌었는지 grep으로 확인**

Run: `grep -n "0071E3\|#0071e3" web_app/static/theme.css`
Expected: 매치 없음 (exit code 1) — `:root` 블록에서 애플 블루가 완전히 제거됨

- [ ] **Step 5: 커밋**

```bash
git add web_app/static/theme.css
git commit -m "feat(design): theme.css 토큰을 HP 디자인 언어 기반으로 재정의"
```

---

### Task 2: 상단바 전역 크롬 — 검색바 · 스캔 버튼 · 마켓 세그먼트 컨트롤

**Files:**
- Modify: `web_app/static/scanner.css:271-294` (`.btn-scan`)
- Modify: `web_app/static/scanner.css:3447-3470` (`.btn-seg-group`, `.btn-seg`)

**Interfaces:**
- Consumes: `--brand`, `--brand-pressed`, `--radius-sharp`, `--radius-pill` (Task 1에서 정의)
- Produces: 없음(리프 컴포넌트 — 다른 태스크가 이 클래스명을 참조하지 않음)

- [ ] **Step 1: `.btn-scan`을 HP 버튼 철학(날카로운 CTA)으로 교체**

`web_app/static/scanner.css:271-288`을 아래로 교체 (radius를 pill→sharp로, hover 색을 `--brand-pressed`로):

```css
.btn-scan {
  height: 34px;
  padding: 0 20px;
  background: var(--brand);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sharp);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background var(--duration-fast);
  white-space: nowrap;
}
.btn-scan:hover { background: var(--brand-pressed); }
.btn-scan:disabled { opacity: 0.5; cursor: not-allowed; }
```

- [ ] **Step 2: 마켓 세그먼트 컨트롤(`.btn-seg`)은 HP의 category-tab처럼 pill 유지, active 배경만 잉크로 통일**

`web_app/static/scanner.css:3447-3470`을 아래로 교체 (radius 값을 `980px` 하드코딩에서 토큰으로만 교체 — 형태는 이미 pill이 맞으므로 유지):

```css
/* ── 버튼 세그먼트 그룹 ───────────────────────────────────────────────── */
.btn-seg-group {
  display: flex;
  gap: 2px;
  background: rgba(0, 0, 0, 0.06);
  border: none;
  border-radius: var(--radius-pill);
  padding: 3px;
  flex-shrink: 0;
}
.btn-seg {
  padding: 4px 14px;
  border: none;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s;
}
.btn-seg:hover { background: rgba(255,255,255,0.5); color: var(--text-primary); }
.btn-seg.active { background: #fff; color: var(--text-primary); box-shadow: var(--shadow-button); }
```

- [ ] **Step 3: grep으로 하드코딩된 옛 hover 색상이 남아있지 않은지 확인**

Run: `grep -n "0077ED" web_app/static/scanner.css`
Expected: 매치 없음

- [ ] **Step 4: 서버 재기동 후 상단바 스캔 버튼이 각지게(4px), 마켓 토글이 여전히 알약형으로 보이는지 브라우저에서 육안 확인**

Run: `curl -s http://localhost:5050/ | grep -o 'btn-scan' | head -1`
Expected: `btn-scan` 출력(템플릿에 클래스가 여전히 존재 — 마크업 깨짐 없음 확인). 이어서 브라우저로 `http://localhost:5050/` 접속해 "스캔" 버튼이 각진 사각형, "미국/한국" 토글이 알약형인지 육안 확인.

- [ ] **Step 5: 커밋**

```bash
git add web_app/static/scanner.css
git commit -m "feat(design): 스캔 버튼·마켓 세그먼트 컨트롤에 HP radius 토큰 적용"
```

---

### Task 3: 유틸리티 밴드 — 디스클레이머 · 매크로 스트립 · 통계바 배경 리듬

**Files:**
- Modify: `web_app/static/scanner.css:27-48` (`.disclaimer-band`)
- Modify: `web_app/static/scanner.css:374-382` (`.stats-bar`)
- Modify: `web_app/static/scanner.css:1518-1527` (`.macro-events-strip`)

**Interfaces:**
- Consumes: `--surface-muted`(포그), `--surface-subtle`(클라우드) (Task 1)
- Produces: 없음

- [ ] **Step 1: 디스클레이머 밴드를 포그 톤으로 (경고성 정보를 가장 조용한 밴드로)**

`web_app/static/scanner.css:37`의 `background: rgba(255, 255, 255, 0.92);`를 아래로 교체:

```css
  background: rgba(232, 232, 232, 0.92);
```

- [ ] **Step 2: 통계바를 클라우드 톤으로 (기존 `var(--card)` 흰색 → 유틸리티 밴드로 구분)**

`web_app/static/scanner.css:375`의 `background: var(--card);`를 아래로 교체:

```css
  background: var(--surface-subtle);
```

- [ ] **Step 3: 매크로 이벤트 스트립의 보라색 그라디언트를 HP 톤(클라우드 단색)으로 교체**

`web_app/static/scanner.css:1521`의 `background: linear-gradient(90deg, rgba(99, 102, 241, 0.06), rgba(139, 92, 246, 0.04));`를 아래로 교체:

```css
  background: var(--surface-subtle);
```

- [ ] **Step 4: grep으로 옛 보라색 그라디언트가 남아있지 않은지 확인**

Run: `grep -n "99, 102, 241, 0.06" web_app/static/scanner.css`
Expected: 매치 없음

- [ ] **Step 5: 브라우저에서 상단바(흰색) 아래 매크로/통계 밴드가 살짝 회색으로 뜨는지 육안 확인 후 커밋**

```bash
git add web_app/static/scanner.css
git commit -m "feat(design): 유틸리티 밴드(디스클레이머/통계바/매크로스트립)에 클라우드·포그 배경 적용"
```

---

### Task 4: 필터 칩 · 등급 배지 · 신호 배지

**Files:**
- Modify: `web_app/static/scanner.css:412-446` (`.chip`, `.chip-count`)
- Modify: `web_app/static/scanner.css:887-888` (`.chip[data-filter="laggard"]`)
- Modify: `web_app/static/scanner.css:3074-3090` (`.grade-badge`)
- Modify: `web_app/static/scanner.css:4701-4703` (`.chip-delta`)

**Interfaces:**
- Consumes: `--brand`, `--brand-soft`, `--radius-pill`, `--radius-badge`, `--stock-up`(=`--success`), `--stock-down`(=`--destructive`) (Task 1)
- Produces: 없음

- [ ] **Step 1: 필터 칩 — active 상태를 브랜드 솔리드에서 HP 스타일(연한 배경+브랜드 텍스트)로, radius를 토큰화**

`web_app/static/scanner.css:412-433`을 아래로 교체:

```css
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 12px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color var(--duration-fast), color var(--duration-fast), background var(--duration-fast);
}
.chip:hover { border-color: var(--brand); color: var(--brand); }
.chip.active {
  background: var(--brand-soft);
  color: var(--brand);
  border-color: var(--brand);
}
```

`.chip-count`(434번 줄 이하)의 `border-radius: 100px;`는 `var(--radius-pill)`로 교체한다.

- [ ] **Step 2: "위험" 필터 칩(laggard)을 `--stock-down` 톤으로 통일**

`web_app/static/scanner.css:887-888`을 아래로 교체:

```css
.chip[data-filter="laggard"] { border-color: var(--destructive); color: var(--destructive); }
.chip[data-filter="laggard"].active { background: var(--destructive); border-color: var(--destructive); color: #fff; }
```

- [ ] **Step 3: "점수급등/신규진입" 델타 칩을 `--stock-up` 톤으로 통일**

`web_app/static/scanner.css:4701-4703`을 아래로 교체:

```css
.chip-delta { border-color: var(--success); color: var(--success); }
.chip-delta:hover { border-color: var(--success); color: var(--success); background: rgba(15,138,95,0.08); }
.chip-delta.active { background: var(--success); border-color: var(--success); color: #fff; }
```

- [ ] **Step 4: 등급 배지 radius를 토큰화 (색상은 스펙에 따라 S/A만 조정, B/C는 유지)**

`web_app/static/scanner.css:3074-3090` 중 `.grade-badge` 본체 규칙(3074번 줄 근처)의 `border-radius` 선언을 `var(--radius-badge)`로 교체하고, 등급별 배경색 규칙을 아래로 교체:

```css
.grade-badge.grade-S { color: #fff; background: #7C3AED; }
.grade-badge.grade-A { color: #fff; background: var(--brand); }
.grade-badge.grade-B { color: #fff; background: #16A34A; }
.grade-badge.grade-C { color: #fff; background: #9CA3AF; }
```

(변경점: `grade-A`만 `#2563EB` 하드코딩에서 `var(--brand)`로 교체. S/B/C는 스펙상 유지 대상이므로 값 변경 없음.)

- [ ] **Step 5: grep으로 grade-A의 옛 하드코딩 블루가 제거됐는지 확인**

Run: `grep -n "grade-A { color: #fff; background: #2563EB" web_app/static/scanner.css`
Expected: 매치 없음

- [ ] **Step 6: 커밋**

```bash
git add web_app/static/scanner.css
git commit -m "feat(design): 필터 칩·등급 배지를 HP 토큰(브랜드/success/destructive)으로 통일"
```

---

### Task 5: 종목 카드 · 드로어 카드 shadow/radius 정리

**Files:**
- Modify: `web_app/static/scanner.css:2824-2836` (`.detail-panel .card`)
- Modify: `web_app/static/scanner.css:2837-2846` (`.dp-disclaimer`)
- Modify: `web_app/static/scanner.css:5354-5359` (`.mece-inner`)

**Interfaces:**
- Consumes: `--radius`(16px, Task 1에서 재정의됨), `--shadow-card` (Task 1)
- Produces: 없음

- [ ] **Step 1: `.detail-panel .card`의 하드코딩된 `18px`/그림자를 토큰으로 교체**

`web_app/static/scanner.css:2824-2836`을 아래로 교체:

```css
.detail-panel .card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
#dp-investor-card,
#dp-midcap-card {
  margin: 12px 20px;
}
.detail-panel .card {
  box-shadow: var(--shadow-card);
}
```

- [ ] **Step 2: `.dp-disclaimer`의 하드코딩된 `18px`도 토큰으로 교체**

`web_app/static/scanner.css:2842`의 `border-radius: 18px;`를 `border-radius: var(--radius);`로 교체.

- [ ] **Step 3: `.mece-inner`의 fallback 값(`var(--radius, 8px)`)을 실제 토큰 참조로 단순화**

`web_app/static/scanner.css:5357`의 `border-radius: var(--radius, 8px);`를 `border-radius: var(--radius);`로 교체 (Task 1에서 `--radius`가 항상 정의되므로 fallback 불필요).

- [ ] **Step 4: grep으로 scanner.css 전역에 남은 하드코딩 `18px` 카드 radius가 없는지 표본 확인**

Run: `grep -n "border-radius: 18px" web_app/static/scanner.css`
Expected: 이번 태스크에서 처리한 3곳 외에 남아있다면 목록으로 출력됨 — 남은 항목이 있으면 같은 패턴(카드류)인지 확인 후 `var(--radius)`로 교체. 카드가 아닌 것(예: 원형 아바타)이면 그대로 둔다.

- [ ] **Step 5: 커밋**

```bash
git add web_app/static/scanner.css
git commit -m "feat(design): 드로어 카드·MECE 카드 radius/shadow를 HP 토큰으로 통일"
```

---

### Task 6: detail.html 인라인 스타일 — 히어로 카드 · 버튼

**Files:**
- Modify: `web_app/templates/detail.html:92-100` (`.hero-card`)

**Interfaces:**
- Consumes: `--radius`, `--shadow-elevated` (Task 1)
- Produces: 없음

- [ ] **Step 1: `.hero-card`의 하드코딩된 `16px`을 토큰으로 교체 (값은 동일하지만 향후 일관성 위해 토큰 참조로 통일)**

`web_app/templates/detail.html:92-100`을 아래로 교체:

```css
.hero-card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow-elevated);
  border: 1px solid var(--border);
  padding: 20px;
  position: relative;
  overflow: hidden;
}
```

- [ ] **Step 2: `detail.html` 안에서 `.card`(230번 줄), `.cs-item`(245번 줄)은 이미 `var(--radius)`/`var(--shadow-card)`를 참조하므로 수정 불필요 — grep으로 확인만 수행**

Run: `grep -n "border-radius: var(--radius)" web_app/templates/detail.html`
Expected: `.card`, `.cs-item` 등 여러 줄이 출력됨(이미 토큰화되어 있어 Task 1만으로 자동 반영됨을 확인)

- [ ] **Step 3: 서버 기동 후 종목 상세 드로어를 열어 히어로 카드가 16px 라운드로 보이는지 육안 확인**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/detail/AAPL` (라우트가 다르면 실제 상세 페이지 진입 경로로 대체 — `scanner.html`에서 종목 클릭 시 열리는 드로어 방식이면 메인 페이지에서 브라우저로 직접 클릭해 확인)
Expected: `200` 또는 드로어가 정상 렌더링

- [ ] **Step 4: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): detail.html 히어로 카드 radius/shadow를 토큰으로 통일"
```

---

### Task 7: compare.html 전체 리스타일

**Files:**
- Modify: `web_app/templates/compare.html:38-172` (인라인 `<style>` 전체)

**Interfaces:**
- Consumes: `--radius-pill`, `--radius`(16px), `--radius-sharp`, `--brand`, `--shadow-card` (Task 1)
- Produces: 없음

- [ ] **Step 1: `.compare-back`(38-50줄)을 pill 유지 + radius 토큰화**

`web_app/templates/compare.html:43`의 `border-radius: 999px;`를 `border-radius: var(--radius-pill);`로 교체.

- [ ] **Step 2: `.compare-empty`(57-64줄), `.compare-card`(65-71줄)를 카드 radius 토큰으로 통일**

`web_app/templates/compare.html:60`의 `border-radius: 18px;`를 `border-radius: var(--radius);`로,
`web_app/templates/compare.html:68`의 `border-radius: 20px;`를 `border-radius: var(--radius);`로 교체.

- [ ] **Step 3: `.compare-signal`(86-95줄)을 pill 토큰으로**

`web_app/templates/compare.html:92`의 `border-radius: 999px;`를 `border-radius: var(--radius-pill);`로 교체.

- [ ] **Step 4: `.compare-chart`(99-105줄), `.compare-row`(120-127줄), `.compare-oneliner`(138-147줄)의 하드코딩 radius를 배지/카드 톤으로 정리**

`web_app/templates/compare.html:101`의 `border-radius: 14px;`를 `border-radius: var(--radius-badge);`로,
`web_app/templates/compare.html:125`의 `border-radius: 12px;`를 `border-radius: var(--radius-badge);`로,
`web_app/templates/compare.html:142`의 `border-radius: 12px;`를 `border-radius: var(--radius-badge);`로 교체.

- [ ] **Step 5: grep으로 이 파일 안에 남은 하드코딩 px radius가 없는지 확인**

Run: `grep -n "border-radius: [0-9]" web_app/templates/compare.html`
Expected: 매치 없음(모두 `var(--radius*)` 토큰 참조로 교체됨)

- [ ] **Step 6: 서버 기동 후 비교 페이지 스모크 테스트**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/compare`
Expected: `200`

- [ ] **Step 7: 커밋**

```bash
git add web_app/templates/compare.html
git commit -m "feat(design): compare.html radius를 HP 토큰 체계로 통일"
```

---

### Task 8: pyramid.html 전체 리스타일 (+ `--accent` 오용 버그 수정)

**Files:**
- Modify: `web_app/templates/pyramid.html:8-145` (인라인 `<style>` 전체)

**Interfaces:**
- Consumes: `--brand`, `--radius-pill`, `--radius`(16px), `--radius-sharp`, `--radius-badge` (Task 1)
- Produces: 없음

**배경:** 이 파일은 `var(--accent)`를 흰 텍스트를 얹는 솔리드 버튼 배경으로 쓰고 있다(예: 30번 줄 `.search-btn`). 그런데 `theme.css`의 `--accent`는 원래 "연한 틴트" 역할(Task 1에서 `#c9e0fc`로 재정의)이라 흰 텍스트와 대비가 나오지 않는 기존 버그다. 이번 작업에서 solid CTA 배경 용도로 쓰인 `var(--accent)`는 모두 `var(--brand)`로 교체한다.

- [ ] **Step 1: solid 배경으로 쓰인 `var(--accent)`를 `var(--brand)`로 전량 교체**

`web_app/templates/pyramid.html`에서 아래 6개 셀렉터의 `var(--accent)` 배경/보더/텍스트 참조를 `var(--brand)`로 교체한다 (틴트 역할이 아니라 전부 solid CTA 또는 강조 보더용이므로):

- Line 28 `.field input:focus,.field select:focus{border-color:var(--accent)}` → `border-color:var(--brand)`
- Line 30 `.search-btn{...background:var(--accent);...}` → `background:var(--brand);`
- Line 51 `.strat-price{...color:var(--accent)}` → `color:var(--brand)`
- Line 52 `.strat-desc{...border-left:3px solid var(--accent)}` → `border-left:3px solid var(--brand)`
- Line 66 `.entry-card:hover{border-color:var(--accent)}` → `border-color:var(--brand)`
- Line 83-84 `.autofill-btn{...border:2px solid var(--accent);color:var(--accent);...}` / `:hover{background:var(--accent);...}` → 모두 `var(--brand)`로
- Line 97 `.calc-field input:focus,.calc-field select:focus{border-color:var(--accent)}` → `border-color:var(--brand)`
- Line 101-102 `.alloc-btn.active{border-color:var(--accent);background:var(--accent);...}` → `var(--brand)`
- Line 103 `.calc-btn{...background:var(--accent);...}` → `background:var(--brand);`
- Line 122 `.stage-badge{...background:var(--accent);...}` → `background:var(--brand);`
- Line 125 `.bar{...background:var(--accent);...}` → `background:var(--brand);`

- [ ] **Step 2: 버튼류 radius를 HP 2단 철학으로 재분류 — CTA는 sharp, pill 형태 유지 대상은 pill로**

`web_app/templates/pyramid.html:15`(`.back-btn`)의 `border-radius:999px`는 `var(--radius-pill)`로 (뒤로가기 링크는 HP category-tab처럼 pill 유지).

`web_app/templates/pyramid.html:30`(`.search-btn`)의 `border-radius:12px`는 `var(--radius-sharp)`로 (주 액션 버튼 — HP 버튼은 날카롭게).

`web_app/templates/pyramid.html:83`(`.autofill-btn`)의 `border-radius:14px`는 `var(--radius-sharp)`로.

`web_app/templates/pyramid.html:103`(`.calc-btn`)의 `border-radius:14px`는 `var(--radius-sharp)`로.

`web_app/templates/pyramid.html:101`(`.alloc-btn`)의 `border-radius:10px`는 `var(--radius-sharp)`로 (버튼류이므로 sharp).

- [ ] **Step 3: 카드류 radius를 카드 토큰으로 통일**

아래 셀렉터의 하드코딩 `border-radius`를 `var(--radius)`(16px)로 교체:
- Line 21 `.search-card` (`18px`)
- Line 91 `.input-card` (`18px`)
- Line 115 `.table-wrap` (`18px`)

아래는 카드보다 작은 인라인 요소이므로 `var(--radius-badge)`(8px)로 교체:
- Line 65 `.entry-card` (`16px`)
- Line 75 `.risk-card` (`14px`)
- Line 110 `.summary-card` (`14px`)

- [ ] **Step 4: grep으로 solid 배경 용도의 `var(--accent)`가 남아있지 않은지 확인**

Run: `grep -n "background:var(--accent)" web_app/templates/pyramid.html`
Expected: 매치 없음

- [ ] **Step 5: 서버 기동 후 피라미딩 계산기 페이지 스모크 테스트**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/pyramid`
Expected: `200`

- [ ] **Step 6: 커밋**

```bash
git add web_app/templates/pyramid.html
git commit -m "fix(design): pyramid.html의 --accent 오용을 --brand로 수정하고 HP radius 토큰 적용"
```

---

### Task 9: 최종 QA — 4개 페이지 시각 스모크 테스트 + 잔여 하드코딩 스윕

**Files:**
- 없음(검증 전용 태스크, 파일 수정 없음)

**Interfaces:**
- Consumes: Task 1~8의 모든 결과물
- Produces: 없음(최종 검증)

- [ ] **Step 1: 서버가 떠 있는지 확인, 아니면 재기동**

Run:
```bash
cd web_app && PORT=5050 python app.py &
sleep 3
```

- [ ] **Step 2: 4개 페이지 모두 200 응답 확인**

Run:
```bash
for p in / /compare /pyramid; do
  echo -n "$p: "; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:5050$p"
done
```
Expected: 세 경로 모두 `200` (`/detail/<ticker>` 라우트가 별도로 존재하면 실제 종목 티커로 동일하게 확인 — 라우트명은 `web_app/app.py`의 `@app.route` 선언에서 확인)

- [ ] **Step 3: 옛 애플 블루/보라 그라디언트가 4개 대상 파일에 전혀 남지 않았는지 grep으로 최종 확인**

Run:
```bash
grep -rn "0071E3\|0077ED\|99, 102, 241, 0.06" web_app/static/theme.css web_app/static/scanner.css web_app/templates/detail.html web_app/templates/compare.html web_app/templates/pyramid.html
```
Expected: 매치 없음 (exit code 1)

- [ ] **Step 4: Playwright로 4개 페이지 스크린샷 확보 후 육안 검토 (기존 `web_app/_browser_e2e.py` 패턴 재사용)**

Run:
```bash
python -c "
import asyncio
from playwright.async_api import async_playwright

async def shot(path, name):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':900})
        await page.goto(f'http://localhost:5050{path}', wait_until='networkidle', timeout=30000)
        await page.screenshot(path=f'web_app/_qa_{name}.png', full_page=True)
        await browser.close()

for path, name in [('/', 'scanner'), ('/compare', 'compare'), ('/pyramid', 'pyramid')]:
    asyncio.run(shot(path, name))
print('done')
"
```
Expected: `web_app/_qa_scanner.png`, `web_app/_qa_compare.png`, `web_app/_qa_pyramid.png` 생성. 각 스크린샷을 열어 다음을 확인:
- 상단바/스캔 버튼이 날카로운 사각형(4px)인지
- 종목 카드/드로어가 부드러운 라운드(16px)인지
- 브랜드 컬러가 애플 블루가 아닌 HP 블루(`#024ad8`)로 보이는지
- 상승/하락 색상이 정상적으로(녹색/빨강) 표시되는지

- [ ] **Step 5: 스크린샷 임시 파일 정리**

Run: `rm -f web_app/_qa_*.png`

- [ ] **Step 6: 서버 종료**

Run: `kill %1` (Step 1에서 백그라운드로 띄운 프로세스 종료 — job 번호가 다르면 `jobs`로 확인 후 종료)

---

## Self-Review Notes

- **스펙 커버리지:** 색상(Task 1,4), 타이포그래피(Pretendard는 이미 로드되어 있어 별도 태스크 불필요 — 폰트 스택 정리는 저위험 후속 작업으로 범위 밖), radius 2단 철학(Task 2,5,6,7,8), elevation 단순화(Task 1,5), 레이아웃 밴드 리듬(Task 3), 컴포넌트별 세부사항(Task 2,4,6,7,8) 모두 태스크로 매핑됨. 다크모드는 스펙대로 범위 제외.
- **플레이스홀더 스캔:** 모든 스텝에 실제 CSS 코드/grep 명령/기대 출력을 명시함 — "적절히 처리" 류 표현 없음.
- **타입/네이밍 일관성:** Task 1에서 정의한 토큰명(`--brand`, `--brand-pressed`, `--brand-soft`, `--radius-sharp`, `--radius-pill`, `--radius-badge`)을 Task 2~8에서 동일하게 참조함을 재확인함.
