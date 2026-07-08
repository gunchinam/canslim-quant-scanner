# 종목 상세 드로워 재설계 — HP 디자인 언어 2차 라운드

## 배경

1차 라운드(`2026-07-08-hp-design-redesign-design.md`, 이미 main에 병합됨)는 `theme.css` 토큰 재정의와 그 자동 캐스케이드 중심이었다. 색상·radius·elevation 변수는 HP 톤으로 바뀌었지만, 드로워(종목 상세 패널) 안의 박스 구조·정보 배치·표기 방식 자체는 거의 그대로였다 — 사용자 피드백: "블루가 블루로, 18px가 16px로 바뀐 정도라 체감이 안 된다."

이번 2차 라운드는 **드로워 내부 컴포넌트를 실제로 재설계**한다. 스캐너 메인 화면, compare.html, pyramid.html은 1차 라운드로 충분하다고 판단해 범위에서 제외하고, `web_app/templates/detail.html`(드로워)에 집중한다.

## 접근 방식 검증: 하드 오프셋 그림자는 HP가 아니다

드로워에는 이미 `.dp-oneliner-poster`/`.dp-verdict-poster`라는 "3px 잉크 테두리 + `6px 6px 0` 하드 오프셋 그림자"의 네오브루탈리즘 포스터 컴포넌트가 존재한다(`web_app/static/scanner.css:2353` 부근). 처음에는 이 패턴을 HP 톤으로 확장하는 안을 제시했으나, `DESIGN-hp.md` 원본과 대조한 결과 **이 하드 그림자 패턴은 HP 스타일이 아님을 확인했다**:

- HP의 Elevation 체계는 Flat → Hairline(1px) → Soft Lift(`0 2px 8px rgba(26,26,26,.08)`) → Floating(`0 8px 24px rgba(26,26,26,.12)`) 4단계뿐이며, 하드 오프셋 그림자 단계가 없다.
- HP 문서의 Do's/Don'ts: "무거운 매테리얼 그림자를 쓰지 말 것 — 깊이는 컬러 대비와 Soft Lift만으로 표현."
- HP의 실제 "굵은 신호"는 `chevron-decoration`(각진 블루 슬래시, `rounded.none`, 그림자 없음)이며, 명시적으로 "히어로 배너 전용, 카드 안 장식 노이즈로 쓰지 말 것"이라 — 여러 곳이 아니라 **1곳 한정**이 원칙이다.

따라서 이번 스펙은 하드 그림자 포스터 패턴을 확장하지 않는다. 대신 HP가 실제로 반복 사용하는 두 가지 장치 — **① 큰 타이포그래피** ②**컬러 대비 배경(brand-soft/cloud)** — 를 "결론을 보여주는" 지점에 광범위하게 적용하고, 각진 슬래시 장식은 히어로 카드 1곳에만 HP 원칙대로 제한한다.

## 범위

- 대상 파일: `web_app/templates/detail.html`(인라인 `<style>`), `web_app/static/scanner.css`(dp-oneliner-poster/dp-verdict-poster가 정의된 부분)
- scanner.html/compare.html/pyramid.html은 범위 밖(1차 라운드로 충분)
- 데이터 나열형 컴포넌트(CAN SLIM 리스트, 투자자 동향, 실적 표, 소유구조/내부자 카드)는 구조 변경 없음 — 1차 라운드에서 이미 `var(--radius)`/`var(--shadow-card)`로 토큰화됨

## 결론 지점 재설계 ("포스터" 대체)

결론/요약 정보(히어로 점수, 원라이너, 판정, 목표가)는 **컬러 대비 배경(`var(--brand-soft)`) + 확대된 타이포그래피**로 "이건 결론이다"를 표시한다. 하드 그림자·두꺼운 테두리는 쓰지 않는다.

### 히어로 카드 (`.hero-card`, `detail.html:92-100`)

**계획 작성 중 발견한 정정 사항**: `.hero-score`(`detail.html:136-141`)는 이미 `font-size: 48px; font-weight: 700;`로 되어 있다 — 애초 제안한 목표 크기와 동일해 이 항목은 변경 불필요.

- 배경: `var(--card)` → `var(--brand-soft)`로 교체 — 다른 흰 카드들과 색 대비로 구분되는 유일한 지점
- `.hero-score`: 변경 없음(이미 48px/700)
- `.hero-grade`(`detail.html:158-163`, 현재 17px/700): **22px, weight 700**으로 확대 — 등급 텍스트도 결론성 정보이므로 히어로 점수에 준하는 무게감 부여
- 그림자: `var(--shadow-card)`(Soft Lift) → `var(--shadow-elevated)`(Floating)로 승격 — 드로워 내 다른 카드보다 한 단계 더 뜬 느낌
- 카드 우측 상단에 각진 블루 슬래시 장식(`chevron-decoration`: `background: var(--brand)`, `border-radius: 0`, 그림자 없음, 삼각형/평행사변형 형태) 1개 배치 — **드로워 전체에서 이 카드 한 곳에만 사용, 다른 카드에는 절대 쓰지 않는다**

### 원라이너 포스터 (`dp-oneliner-poster`, `scanner.css:2353-2441`)

**계획 작성 중 발견한 정정 사항**: 처음 스펙에서는 이 요소를 "베이지 배경 하나"로 가정했으나, 실제로는 `[data-tag="..."]` 어트리뷰트로 16종의 판정 태그(TRUE_VALUE, VALUE_TRAP, BUBBLE, STRONG_BUY, AVOID 등)마다 서로 다른 `background`/`color`/`border-color`/`box-shadow` 색을 쓰는 의도적인 시맨틱 색상 체계였다(`scanner.css:2388-2441`). 이 색 구분은 HP 스타일과 무관하게 그 자체로 유의미한 정보(어떤 판정 태그인지)이므로 **보존한다**. 이번 라운드에서 손대는 건 "하드 오프셋 그림자"라는 형태 자체이지, 태그별 색상이 아니다.

- `border`: 각 `[data-tag]` 변형의 `border-color`(태그 고유 색)는 유지하되, 두께만 `3px` → `2px`로 살짝 얇게
- `box-shadow: 6px 6px 0 <태그색>` → `var(--shadow-elevated)`로 교체 — 하드 오프셋 그림자 형태를 폐기하고 HP의 Floating 단계로 통일(그림자 자체는 무채색 처리, 태그색은 border/background에서만 표현)
- `background`/`color`: 16개 `[data-tag]` 변형 그대로 유지 — **변경하지 않음**
- 텍스트 크기(`clamp(30px, 5.5vw, 46px)`)는 유지 — 이미 HP식 큰 타이포그래피 원칙에 부합
- 기본 `.dp-oneliner-poster` 규칙(태그 미지정 시 폴백)의 `background: #F4ECD8` 배경만 `var(--brand-soft)`로 교체(태그가 없는 경우에 한정된 변경)

### 판정 카드 (`dp-verdict-poster`, `scanner.css:2578-2602`) — 범위 제외

**계획 작성 중 발견한 정정 사항**: 이 요소는 하드 오프셋 그림자나 베이지 배경을 쓰지 않는다 — 실제로는 `dvp-green`/`dvp-yellow`/`dvp-red` 신호등 그라디언트 배경에 `inset 0 1px 0 rgba(255,255,255,.22)` 소프트 하이라이트만 쓰는, 이미 HP의 "무거운 그림자 없이 컬러로 신호"라는 원칙에 가까운 컴포넌트였다. 애초 스펙 작성 시 `dp-oneliner-poster`와 혼동해 잘못 기술한 것으로 확인 — **이번 라운드에서 수정하지 않는다.** 코너 radius(`18px 18px 0 0`, 상단만 둥근 부분 radius)도 1차 라운드 Task 5 리뷰에서 "포스터류는 카드 radius 토큰화 대상이 아니다"로 이미 확정된 사항이라 그대로 둔다.

### 목표가/컨센서스 박스 (`#detail-aux-box`, 컨센서스 카드, `detail.html:1152`, `1185` 부근)

**계획 작성 중 발견한 사항**: `#detail-aux-box`의 현재 `background: var(--bg-tertiary)`는 `theme.css`에 정의되지 않은(폴백도 없는) 변수라 실제로는 배경이 비어 보이는 기존 버그였다. 이번 교체로 이 버그도 함께 해결된다.

- 배경: `var(--bg-tertiary)`(미정의, 사실상 무배경) → `var(--brand-soft)`로 교체
- 목표가 숫자(`#detail-target`, `#detail-broker-target`): 현재 인라인 크기(15px) → **24~28px, weight 600**으로 확대(HP `display-md`급)

## 데이터 나열 카드 · 섹션 그룹화

구조는 그대로 두되, 각 카드 그룹 위에 `var(--surface-subtle)`(클라우드) 배경의 얇은 섹션 라벨 밴드를 추가해 그룹 경계를 명확히 한다. 대상: "투자자 동향"(`dp-investor-card`), "실적 한눈에"(`detail-earnings-card`) 등 현재 인라인 텍스트 헤더로만 표시되던 섹션.

- 밴드: `background: var(--surface-subtle)`, `padding: 6px 16px`, `font-size: 11px`, `font-weight: 700`, `letter-spacing: 0.03em`, 카드 상단에 고정 배치(카드 자체와 한 몸으로, 카드 밖 별도 요소 아님)
- 카드 본문(리스트/표)은 흰 배경 그대로 유지 — 밴드만 클라우드색으로 얹어서 "이 카드가 어떤 그룹인지"를 표시

## 등급/신호 배지

- `.hero-grade`(히어로 카드 안 신호 등급 텍스트): 폰트 크기 확대(현재 대비 약 1.3배), 색상은 1차 라운드에서 이미 토큰화된 `--grade-s/a/b/c` 값 재사용 — 색 변경 없음
- `.risk-badge`, `.sig-tag-hot/warn/info`: 1차 라운드에서 이미 `var(--radius-badge)`(8px)로 통일돼 있음을 확인 — 이번 라운드에서 추가 변경 없음

## 반응형 고려사항

- 모바일(<744px)에서 히어로 카드의 chevron 슬래시 장식은 HP 원칙(`Collapsing Strategy: 칩 도 데코레이션은 모바일에서 축소·생략`)에 따라 숨김 처리 — 좁은 화면에서 장식이 숫자를 가리지 않도록
- 확대된 타이포그래피(히어로 점수 48px 등)는 모바일에서 별도 축소 없이 유지 — 드로워는 이미 모바일 전체화면으로 열리므로 폭 여유가 있음(기존 `.hero-wrap` 반응형 padding 규칙 그대로 적용)

## 알려진 제약

- `chevron-decoration`의 정확한 형태(각도·크기)는 SVG 또는 CSS `clip-path`로 구현 가능하나, 이 스펙에서는 "각진 블루 평행사변형, 그림자 없음, 히어로 카드 우상단 1곳"이라는 배치·색상·개수 원칙만 확정한다. 정확한 clip-path 좌표는 구현 단계에서 시각적으로 조정한다.
- `var(--brand-soft)`(#c9e0fc)를 히어로/포스터/목표가 등 여러 곳에서 반복 사용하므로, 실제 렌더링 시 서로 다른 섹션이 과도하게 비슷한 톤으로 뭉쳐 보이지 않는지 구현 후 스크린샷으로 확인이 필요하다.
