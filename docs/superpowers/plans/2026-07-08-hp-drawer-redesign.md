# 종목 상세 드로워 재설계 2차 라운드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 상세 드로워(`web_app/templates/detail.html`)의 "결론을 보여주는" 지점(히어로 카드, 목표가 박스, 컨센서스 카드)을 컬러 대비 배경(`var(--brand-soft)`)과 확대된 타이포그래피로 승격하고, 데이터 나열 카드(투자자 동향, 실적 한눈에)에는 섹션 구분용 클라우드 밴드를 추가한다.

**Architecture:** 1차 라운드(이미 병합됨)에서 정의된 `theme.css` 토큰(`--brand-soft`, `--surface-subtle`, `--radius` 등)만 재사용하며, 새 토큰은 만들지 않는다. 모든 변경은 `web_app/templates/detail.html` 한 파일(인라인 `<style>` + 마크업)에 국한된다.

**Tech Stack:** 순수 CSS(인라인 `<style>` 블록), Jinja2 템플릿 마크업, Flask 개발 서버, Playwright(시각 검증).

## Global Constraints

- 대상 파일은 `web_app/templates/detail.html` 하나뿐이다. `scanner.css`, `theme.css`, 다른 템플릿은 이번 라운드에서 건드리지 않는다.
- `.hero-oneliner`(`detail.html:788-1026`)와 `dp-verdict-poster`는 **완전히 범위 제외** — 어떤 태스크도 이 두 컴포넌트의 CSS/마크업을 수정하지 않는다. (사유: `.hero-oneliner`는 16개 판정 태그마다 halftone/줄무늬/대각선 텍스처 오버레이까지 갖춘 손으로 제작된 트레이딩 카드 아트이고, `dp-verdict-poster`는 이미 신호등 그라디언트+소프트 하이라이트로 HP 원칙에 부합하는 컴포넌트였다.)
- 데이터 나열 카드(CAN SLIM 리스트, 소유구조/내부자 카드, 실적 표 본문)는 구조·배경색을 바꾸지 않는다 — 1차 라운드에서 이미 `var(--radius)`/`var(--shadow-card)`로 토큰화되어 흰 배경 그대로 둔다.
- 사용할 색상 토큰은 `var(--brand-soft)`(#c9e0fc, 결론 지점 배경), `var(--surface-subtle)`(#f7f7f7, 섹션 라벨 밴드 배경) 두 가지뿐 — 새 hex 값을 발명하지 않는다.

---

## File Structure

새 파일은 만들지 않는다. 기존 `web_app/templates/detail.html` 하나만 수정한다 — 12~1098번 줄의 인라인 `<style>` 블록과 1120번 줄 이후의 HTML 마크업 양쪽 모두.

---

### Task 1: 히어로 카드 배경 · 등급 폰트 확대

**Files:**
- Modify: `web_app/templates/detail.html:92-100` (`.hero-card`)
- Modify: `web_app/templates/detail.html:158-163` (`.hero-grade`)

**Interfaces:**
- Consumes: `--brand-soft`(1차 라운드 theme.css에서 정의됨)
- Produces: 없음(리프 컴포넌트)

**계획 작성 시 확인한 사항**: `.hero-card`는 1차 라운드 Task 6에서 이미 `border-radius: var(--radius)`, `box-shadow: var(--shadow-elevated)`로 토큰화되어 있다 — 이번 태스크에서 radius/shadow는 손대지 않고 `background`만 바꾼다.

- [ ] **Step 1: `.hero-card` 배경을 브랜드 틴트로 교체**

`web_app/templates/detail.html:92-100`을 아래로 교체:

```css
.hero-card {
  background: var(--brand-soft);
  border-radius: var(--radius);
  box-shadow: var(--shadow-elevated);
  border: 1px solid var(--border);
  padding: 20px;
  position: relative;
  overflow: hidden;
}
```

- [ ] **Step 2: `.hero-grade`(등급 텍스트) 폰트 확대**

`web_app/templates/detail.html:158-163`을 아래로 교체:

```css
.hero-grade {
  font-size: 22px;
  font-weight: 700;
  color: var(--brand);
  align-self: center;
}
```

- [ ] **Step 3: grep으로 변경 확인**

Run: `grep -n "background: var(--brand-soft);" web_app/templates/detail.html`
Expected: `.hero-card` 블록 안에서 1개 매치

Run: `grep -n "font-size: 22px;" web_app/templates/detail.html`
Expected: `.hero-grade` 블록 안에서 1개 매치

- [ ] **Step 4: 서버 기동 후 스모크 테스트**

Run:
```bash
cd web_app && PORT=5061 python app.py &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5061/
```
Expected: `200`

- [ ] **Step 5: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 드로워 히어로 카드 배경을 brand-soft로, 등급 텍스트 확대"
```

---

### Task 2: 히어로 카드 chevron 슬래시 장식 (+ 모바일 숨김)

**Files:**
- Modify: `web_app/templates/detail.html` (새 CSS 클래스 추가 — `.hero-watermark` 규칙 직후, 약 190번 줄 부근)
- Modify: `web_app/templates/detail.html:1122-1123` (히어로 카드 마크업에 장식 요소 추가)
- Modify: `web_app/templates/detail.html` (768px 모바일 브레이크포인트 블록, 약 1044-1047번 줄 부근)

**Interfaces:**
- Consumes: `--brand`(1차 라운드 theme.css)
- Produces: 없음

이 태스크는 HP 문서의 `chevron-decoration`(각진 블루 슬래시, `rounded.none`, 그림자 없음, 히어로 배너 전용)을 드로워 히어로 카드 1곳에 적용하는 시각적 판단이 필요한 작업이다. 아래 시작 CSS로 구현한 뒤, **반드시 스크린샷으로 확인**하고 우측 상단 "종합점수" 배지(`.hero-sector`)나 본문 텍스트와 겹치지 않는지 검증한다. 겹치면 `width`/`height` 값을 좁혀 재조정한다(색상·위치(우상단)·그림자 없음 원칙은 유지).

- [ ] **Step 1: `.hero-chevron` CSS 클래스 추가**

`web_app/templates/detail.html`에서 `.hero-watermark { ... }` 규칙(183-189번 줄 부근) 바로 다음에 아래 규칙을 추가:

```css
.hero-chevron {
  position: absolute;
  top: 0;
  right: 0;
  width: 28px;
  height: 44px;
  background: var(--brand);
  clip-path: polygon(100% 0, 100% 100%, 0 100%, 60% 0);
  pointer-events: none;
  z-index: -1;
}
```

(`z-index: -1`은 `.hero-card`가 `position: relative`로 새 스태킹 컨텍스트를 만들기 때문에 카드 배경보다는 위, 카드 안의 일반 흐름 텍스트보다는 아래에 놓이게 하기 위함 — 텍스트를 가리지 않으면서 배경 위에는 보이도록.)

- [ ] **Step 2: 히어로 카드 마크업에 장식 요소 추가**

`web_app/templates/detail.html:1122-1124`을 아래로 교체(기존 `<div class="hero-card">` 다음 줄에 장식 div 추가):

```html
    <div class="hero-wrap">
      <div class="hero-card">
        <div class="hero-chevron" aria-hidden="true"></div>
        <div id="detail-oneliner" class="hero-oneliner" style="display:none;"></div>
```

- [ ] **Step 3: 서버 기동 후 스크린샷으로 겹침 여부 확인**

Run:
```bash
cd web_app && PORT=5062 python app.py &
sleep 3
python -c "
import asyncio
from playwright.async_api import async_playwright

async def shot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':480,'height':900})
        await page.goto('http://localhost:5062/', wait_until='networkidle', timeout=30000)
        await page.evaluate('''() => {
            const cards = document.querySelectorAll('.stock-row, .stock-card, [data-ticker]');
            if (cards.length) cards[0].click();
        }''')
        await page.wait_for_timeout(1500)
        await page.screenshot(path='_chevron_check.png')
        await browser.close()

asyncio.run(shot())
"
```
Expected: `_chevron_check.png` 생성. 이 이미지를 Read 툴로 열어 육안 확인:
- 우상단 파란 슬래시가 `.hero-sector`(섹터 배지) 텍스트나 히어로 점수 숫자를 가리지 않는지
- 카드 모서리 radius 밖으로 슬래시가 삐져나오지 않는지(카드의 `overflow: hidden`이 자동으로 잘라주는지)

겹치거나 어색하면 Step 1의 `width`/`height` 값을 줄여 다시 시도한다(예: `width: 20px; height: 36px;`).

- [ ] **Step 4: 확인 후 스크린샷 삭제**

Run: `rm -f _chevron_check.png`

- [ ] **Step 5: 모바일(768px 이하)에서 chevron 숨김**

`web_app/templates/detail.html`의 `@media (max-width: 768px)` 블록 안, `.hero-card { padding: 16px; }` 줄(1044번 줄 부근) 바로 다음에 추가:

```css
  .hero-chevron { display: none; }
```

- [ ] **Step 6: 서버 재기동 후 최종 확인**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/`
Expected: `200`

- [ ] **Step 7: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 히어로 카드에 HP chevron 슬래시 장식 추가(모바일 숨김)"
```

---

### Task 3: 목표가 박스 브랜드 틴트 배경 + 숫자 확대

**Files:**
- Modify: `web_app/templates/detail.html:1152-1163` (`#detail-aux-box` 마크업)

**Interfaces:**
- Consumes: `--brand-soft`(1차 라운드)
- Produces: 없음

**계획 작성 시 확인한 사항**: 현재 `#detail-aux-box`는 `background:var(--bg-tertiary)`를 쓰는데, `--bg-tertiary`는 `theme.css`에 정의되지 않은(폴백도 없는) 변수라 실제로는 배경이 비어 보이는 기존 버그다. 이번 교체로 이 버그도 함께 해결된다.

- [ ] **Step 1: 배경 교체 + 목표가 숫자 확대**

`web_app/templates/detail.html:1152-1163`을 아래로 교체:

```html
          <div id="detail-aux-box" style="padding:10px 12px; border:1px solid var(--border); border-radius:12px; background:var(--brand-soft);">
            <div id="detail-aux-label" style="font-size:11px; font-weight:700; color:var(--text-tertiary); margin-bottom:4px;">목표가</div>
            <div id="detail-dcf-line">DCF 적정가 <strong id="detail-target" style="font-size:24px;font-weight:600;">—</strong> <span id="detail-dcf-upside" style="font-size:11px;font-weight:700;margin-left:2px;"></span> <span id="detail-target-src" style="font-size:10px;color:var(--text-tertiary);margin-left:4px;"></span></div>
            <div id="detail-broker-line" style="margin-top:4px;">
              <div style="display:flex; align-items:baseline; gap:6px; flex-wrap:wrap;">
                <span id="detail-broker-label" style="font-weight:700;">증권사 목표가</span>
                <strong id="detail-broker-target" style="font-size:24px;font-weight:600;">—</strong>
                <span id="detail-broker-upside" style="font-size:12px;font-weight:700;"></span>
              </div>
              <div id="detail-broker-src" style="font-size:11px;color:var(--text-tertiary);margin-top:3px;line-height:1.4;"></div>
            </div>
          </div>
```

- [ ] **Step 2: grep으로 옛 미정의 변수가 제거됐는지 확인**

Run: `grep -n "var(--bg-tertiary)" web_app/templates/detail.html`
Expected: `#detail-aux-box` 관련 매치 없음 (이 줄에서는 제거됨 — 파일의 다른 곳에 `--bg-tertiary`가 남아있어도 이번 태스크와 무관하므로 무시)

- [ ] **Step 3: 서버 기동 후 스모크 테스트**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/
```
Expected: `200` (Task 2에서 띄운 서버가 아직 떠 있지 않다면 `cd web_app && PORT=5062 python app.py &` 후 `sleep 3`)

- [ ] **Step 4: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 목표가 박스 배경을 brand-soft로 교체(미정의 변수 버그 수정 겸)하고 숫자 확대"
```

---

### Task 4: 컨센서스 카드 브랜드 틴트 배경

**Files:**
- Modify: `web_app/templates/detail.html` (새 CSS 규칙 추가 — `.card { ... }` 규칙 직후, 약 235번 줄 부근)

**Interfaces:**
- Consumes: `--brand-soft`(1차 라운드)
- Produces: 없음

`#consensus-wrap`은 공용 `.card` 클래스(배경 `var(--card)`, 흰색)를 쓰는데 이 클래스는 드로워 전체에서 데이터 나열 카드에도 공유되므로 `.card` 자체를 바꾸지 않고, `#consensus-wrap` 안의 `.card`만 별도 규칙으로 덮어쓴다.

- [ ] **Step 1: 스코프 한정 배경 규칙 추가**

`web_app/templates/detail.html`에서 `.card { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow-card); border: 1px solid var(--border); }` 규칙(230-235번 줄 부근) 바로 다음에 추가:

```css
#consensus-wrap .card {
  background: var(--brand-soft);
}
```

- [ ] **Step 2: grep으로 규칙이 정확히 추가됐는지 확인**

Run: `grep -n "#consensus-wrap .card" web_app/templates/detail.html`
Expected: 1개 매치

- [ ] **Step 3: 서버 기동 후 스모크 테스트**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/`
Expected: `200`

- [ ] **Step 4: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 컨센서스 카드 배경을 brand-soft로 교체"
```

---

### Task 5: 투자자 동향 카드 섹션 라벨 밴드

**Files:**
- Modify: `web_app/templates/detail.html:1205` (`dp-investor-card` 헤더 div)

**Interfaces:**
- Consumes: `--surface-subtle`(1차 라운드)
- Produces: 없음

카드 자체(`.card`)는 이미 `padding:0; overflow:hidden;`이라 헤더 div가 카드 상단에 딱 붙어 있다 — 배경색만 추가하면 자연스럽게 "밴드"가 된다.

- [ ] **Step 1: 헤더 div에 클라우드 배경 추가**

`web_app/templates/detail.html:1205`을 아래로 교체:

```html
        <div style="padding:12px 16px 8px; font-size:12px; font-weight:700; color:var(--text-tertiary); letter-spacing:0.03em; background:var(--surface-subtle);">투자자 동향</div>
```

- [ ] **Step 2: grep으로 확인**

Run: `grep -n "투자자 동향" web_app/templates/detail.html`
Expected: 해당 줄에 `background:var(--surface-subtle);` 포함되어 있음

- [ ] **Step 3: 서버 기동 후 스모크 테스트**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/`
Expected: `200`

- [ ] **Step 4: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 투자자 동향 카드 헤더에 클라우드 섹션 밴드 적용"
```

---

### Task 6: 실적 한눈에 카드 섹션 라벨 밴드

**Files:**
- Modify: `web_app/templates/detail.html:1174-1182` (`detail-earnings-card` 마크업)

**Interfaces:**
- Consumes: `--surface-subtle`(1차 라운드)
- Produces: 없음

이 카드는 `dp-investor-card`와 달리 `.card`에 `padding:14px 16px`가 통째로 적용돼 있어 헤더가 카드 안쪽에 들어가 있다. `dp-investor-card`와 동일한 "밴드" 패턴을 만들려면 `.card`의 padding을 0으로 바꾸고 헤더/본문에 각자 padding을 부여하는 구조 조정이 필요하다.

- [ ] **Step 1: 카드 구조를 밴드+본문으로 분리**

`web_app/templates/detail.html:1174-1182`를 아래로 교체:

```html
    <div id="detail-earnings-card" style="padding:12px 24px 0; display:none;">
      <div class="card" style="padding:0; overflow:hidden;">
        <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 16px; background:var(--surface-subtle);">
          <span style="font-size:13px; font-weight:700; color:var(--text-primary);">📈 실적 한눈에</span>
          <span style="font-size:10px; font-weight:500; color:var(--text-tertiary);">자세히는 재무 지표 탭</span>
        </div>
        <div id="detail-earnings-chips" style="display:flex; gap:8px; flex-wrap:wrap; padding:12px 16px;"></div>
      </div>
    </div>
```

- [ ] **Step 2: grep으로 확인**

Run: `grep -n "실적 한눈에" web_app/templates/detail.html`
Expected: 해당 줄 근처에 `background:var(--surface-subtle);` 포함

- [ ] **Step 3: 서버 기동 후 스모크 테스트 + 시각 확인**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/`
Expected: `200`

이 태스크는 padding을 카드 레벨에서 내부 div 레벨로 옮기는 구조 변경이므로, `detail-earnings-chips`(칩 목록)가 카드 좌우 여백 없이 붙어 보이지 않는지 스크린샷으로 한 번 확인한다(Task 2의 Step 3 스크린샷 스크립트를 재사용하되 경로를 `_earnings_check.png`로 바꿔서 실행 — 단, `detail-earnings-card`는 실적 데이터가 있는 종목에서만 `display:none`이 풀리므로, 로컬에서 실적 데이터가 있는 종목을 하나 열어서 확인해야 한다. 확인이 어려우면 이 사실을 보고에 남기고 다음 단계로 진행한다).

- [ ] **Step 4: 커밋**

```bash
git add web_app/templates/detail.html
git commit -m "feat(design): 실적 한눈에 카드 헤더를 클라우드 섹션 밴드 구조로 분리"
```

---

### Task 7: 최종 QA — 드로워 시각 검증 + 회귀 테스트

**Files:**
- 없음(검증 전용, 파일 수정 없음)

**Interfaces:**
- Consumes: Task 1~6의 모든 결과물
- Produces: 없음

- [ ] **Step 1: 서버 기동 확인(안 떠 있으면 기동)**

Run:
```bash
cd web_app && PORT=5062 python app.py &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5062/
```
Expected: `200`

- [ ] **Step 2: 드로워 스크린샷 확보**

Run:
```bash
python -c "
import asyncio
from playwright.async_api import async_playwright

async def shot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':480,'height':1000})
        await page.goto('http://localhost:5062/', wait_until='networkidle', timeout=30000)
        await page.evaluate('''() => {
            const cards = document.querySelectorAll('.stock-row, .stock-card, [data-ticker]');
            if (cards.length) cards[0].click();
        }''')
        await page.wait_for_timeout(1500)
        await page.screenshot(path='_qa_drawer.png', full_page=True)
        await browser.close()

asyncio.run(shot())
"
```
Expected: `_qa_drawer.png` 생성

- [ ] **Step 3: 스크린샷 육안 검증**

`_qa_drawer.png`를 Read 툴로 열어 아래를 확인:
- 히어로 카드가 연한 블루 배경(`brand-soft`)으로 다른 흰 카드들과 구분되는지
- 히어로 카드 우상단에 파란 슬래시 장식이 텍스트와 겹치지 않고 보이는지
- 등급 텍스트가 이전보다 커졌는지
- 목표가 숫자(있는 경우)가 커지고 박스 배경이 연한 블루인지
- 투자자 동향/실적 카드(데이터가 있는 경우)에 회색 섹션 라벨 밴드가 보이는지
- CAN SLIM 리스트 등 데이터 나열 카드는 흰 배경 그대로인지(변경 없어야 함)
- 레이아웃 깨짐(텍스트 겹침, 카드 잘림)이 없는지

- [ ] **Step 4: 스크린샷 삭제**

Run: `rm -f _qa_drawer.png`

- [ ] **Step 5: pytest 회귀 확인**

Run: `cd web_app && python -m pytest tests/ -q`
Expected: `195 passed, 10 failed` — 1차 라운드에서 확인된 기존 베이스라인과 동일해야 함(`test_history_timeline.py`, `test_chat_client_fallback.py`의 10개 실패는 이번 작업과 무관한 기존 실패). 이 숫자와 다르면(특히 195보다 적게 통과하면) 회귀이므로 BLOCKED로 보고한다.

- [ ] **Step 6: 서버 종료**

Run: `kill %1` (백그라운드 job 번호가 다르면 `jobs`로 확인 후 종료)

---

## Self-Review Notes

- **스펙 커버리지**: 히어로 카드 배경/등급(Task 1), chevron 장식(Task 2), 목표가 박스(Task 3), 컨센서스 카드(Task 4), 투자자 동향/실적 섹션 밴드(Task 5, 6) 모두 스펙의 "결론 지점 재설계"·"데이터 나열 카드·섹션 그룹화" 절과 1:1 매핑됨. `.hero-oneliner`/`dp-verdict-poster`는 스펙에서 명시적으로 제외됐으므로 태스크 없음(의도적).
- **플레이스홀더 스캔**: 모든 스텝에 실제 HTML/CSS 코드, grep 명령, 기대 출력을 명시함.
- **타입/네이밍 일관성**: 전 태스크에서 `var(--brand-soft)`, `var(--surface-subtle)` 두 토큰만 재사용하고 새 토큰을 만들지 않음 — 1차 라운드 theme.css와 이름 충돌 없음.
