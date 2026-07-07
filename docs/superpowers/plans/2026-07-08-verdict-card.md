# 드로어 종합 판정 카드 (Verdict Card) Implementation Plan

**Goal:** 드로어의 분산된 신호(밸류에이션·재무건전성·타이밍 리스크)를 규칙 기반으로 합성한 "종합 판정 카드"를 드로어 최상단에 추가한다. 사용자가 "그래서 사라는 거야?"에 대한 답(매수 적기/분할 접근/관망/회피)과 근거, 행동 트리거를 한눈에 보게 한다.

**Architecture:** 백엔드 변경 없음. 프론트(app.js)에 순수 합성 함수 `_composeVerdict()`를 추가하고, 3개 데이터 소스가 도착할 때마다 카드를 점진 갱신한다. 판정 규칙은 순수 함수로 격리해 기존 `test_entry_label_js.py` 패턴(node로 JS 함수 추출 실행)으로 pytest 검증한다.

## 데이터 소스 (이미 존재, 신규 API 없음)

| 소스 | 로드 시점 | 사용 필드 |
|---|---|---|
| `/api/ticker` → `_lastDetailData` (d) | 드로어 열릴 때 즉시 | `Price`, `PiotroskiF`, `AltmanZ`, `AltmanZone`, `EntryPlan.{mdd_current, dd_velocity_5d, underwater_days, calmar_ratio}` |
| `/api/nomura-score/<t>` → `json.data` | **신규: 드로어 열릴 때 eager fetch** (기존엔 아코디언 toggle 시에만) | `football_field[{method,min_price,max_price}]`, `current_price`, `quantitative_score`, `nomura_upside`, `piotroski`, `altman_z` |
| `/api/four_axis/<t>` | 기존 IntersectionObserver lazy 로드 재사용 — **중복 fetch 금지** (차트 렌더가 무거움). `loadDpFourAxis` 성공 지점에서 모듈 변수 `_dpFourAxisData`에 저장 + `document.dispatchEvent(new CustomEvent('dp-fouraxis-loaded'))` | `trend.score`, `momentum.score`, `volume.score`, `signal_stars` |

## 판정 규칙 (순수 함수 `_composeVerdict(detail, nomura, fourAxis)`)

각 인자는 null 허용(미도착). 반환: `{verdict, label, reasons[], triggers[], confidence, axes}`.

### 축 1: 품질(quality) — detail 우선, nomura로 보강
- `piotroski = nomura?.piotroski ?? d.PiotroskiF`, `altmanZ = nomura?.altman_z ?? d.AltmanZ`
- **red**: `altmanZ < 1.81` OR `piotroski <= 3`
- **good**: `altmanZ > 2.99` AND `piotroski >= 6` (piotroski 결측 시 `quantitative_score >= 75`로 대체)
- 그 외 **mid**. 둘 다 결측이면 축 자체 null.

### 축 2: 밸류에이션(valuation) — nomura 필요
- `football_field` 각 밴드에 대해 `price > max_price`(above) / `price < min_price`(below) 판정
- **expensive**: above 밴드 수 ≥ ⌈n/2⌉, 또는 (above ≥ 1 AND `nomura_upside < -10`)
- **cheap**: below 밴드 수 ≥ ⌈n/2⌉, 또는 `nomura_upside >= 15`
- 그 외 **fair**. football_field 비어있고 upside도 없으면 null.

### 축 3: 타이밍(timing) — detail의 EntryPlan + four_axis 보강
- **knife**: `dd_velocity_5d <= -5` (5일간 5%p 이상 낙폭 가속 = 칼날)
- **weak**: `dd_velocity_5d <= -2` OR `mdd_current <= -20` OR `fourAxis.momentum.score <= 2` OR `fourAxis.volume.score <= 1`
- **strong**: `trend.score >= 4` AND `momentum.score >= 4` AND velocity > -2
- 그 외 **ok**. EntryPlan·fourAxis 둘 다 결측이면 null.

### 판정 매트릭스 (우선순위 순서대로 first-match)
1. quality **red** → `AVOID` "회피 — 재무 위험 신호"
2. timing **knife** → `WAIT` "관망 — 급락 진행 중 (추격 금지)"
3. valuation **expensive** → `WAIT` "관망 — 밸류에이션 부담"
4. quality **good** AND valuation **cheap** AND timing **strong** → `BUY` "매수 적기"
5. valuation != expensive AND timing NOT IN (knife, weak) → `SPLIT` "분할 접근 — 아래 분할매수 플랜 참조"
6. timing **weak** (위 1~3 미해당) → `WAIT` "관망 — 수급/모멘텀 약함"
7. 유효 축 ≤ 1개 → `HOLD` "판단 보류 — 데이터 수집 중"

### confidence
유효(non-null) 축 개수: 3 → `높음`, 2 → `중간`, ≤1 → `낮음`.

### reasons (각 축당 1줄, 최대 3줄)
축 상태를 사람 말로. 예: "재무 건전 (Altman 안전 · F6)" / "DCF 밴드 상단 262,161 초과 — 고평가" / "5일간 -10.5%p 급락 진행 중". 근거 숫자는 실제 값 삽입.

### triggers (판정별)
- expensive → `"◯◯원 (◯◯ 밴드 상단) 이하 진입 시 재검토"` — above 밴드 중 max_price가 가장 낮은 것 사용
- knife/weak → `"낙폭 속도 진정(-2%p 이내) 후 재검토"`
- SPLIT/BUY → `"진입 시 하단 분할매수 플랜 참조"` (클릭 시 `dp-split-plan`으로 스크롤)

## Tasks

### Task 1: 순수 함수 + 테스트 (TDD)
- `app.js`에 `_composeVerdict(detail, nomura, fourAxis)` 추가 (DOM 접근 금지, 순수 함수)
- `web_app/tests/test_verdict_card_js.py` 신규 — `test_entry_label_js.py`의 함수 추출 패턴 복사. 케이스: ① knife → WAIT ② expensive(스크린샷 재현: price 296000 > DCF max 262161) → WAIT ③ quality red → AVOID (knife와 동시일 때 AVOID 우선) ④ good+cheap+strong → BUY ⑤ 평범 → SPLIT ⑥ nomura 결측 → 축 2개, confidence 중간 ⑦ 전부 결측 → HOLD

### Task 2: 렌더러 + 오케스트레이션
- `_renderVerdictCard(result)` — 컨테이너 `dp-verdict-card` (scanner.html의 드로어 마크업에서 상세 패널 상단, 리스크/노무라 섹션보다 위에 삽입. `dp-drawdown-risk`·`dp-nomura-inline`가 있는 위치 참조)
- 판정별 색: BUY `#16A34A` / SPLIT `#3182F6` / WAIT `#F59E0B` / AVOID `#DC2626` / HOLD 회색
- 카드 구성: 판정 뱃지 + 한줄 라벨 + 근거 리스트(축별) + 트리거 + confidence 칩
- 오케스트레이션: 상세 패널 populate 함수(app.js ~3191, `_renderDrawdownRisk(d)` 호출 지점)에서 ① detail만으로 1차 렌더 ② `/api/nomura-score` eager fetch 후 재렌더 ③ `dp-fouraxis-loaded` 커스텀 이벤트 수신 시 재렌더. 티커 전환 시 stale 응답 가드(기존 `reqSeq` 패턴 참조).
- `loadDpFourAxis` 성공 지점에 `_dpFourAxisData = d; document.dispatchEvent(...)` 2줄 추가 (four_axis 중복 fetch 금지)
- 트리거의 "분할매수 플랜 참조" 클릭 → `document.getElementById('dp-split-plan')?.scrollIntoView({behavior:'smooth'})`

### Task 3: CSS
- `scanner.css`에 `.vc-card`, `.vc-badge`, `.vc-reason`, `.vc-trigger`, `.vc-conf` — 기존 spl-panel 톤과 통일

### Task 4: 검증
- `python -m pytest web_app/tests/test_verdict_card_js.py -v` 전체 통과
- `node --check web_app/static/app.js`
- 기존 테스트 회귀: `python -m pytest web_app/tests/test_entry_label_js.py web_app/tests/test_fib_dca_plan_js.py -v`

## Global Constraints
- 백엔드(app.py) 수정 금지, 신규 API 금지
- four_axis 중복 fetch 금지 (이벤트 구독만)
- `_composeVerdict`는 순수 함수 유지 (테스트 추출 가능해야 함)
- 커밋 시 이 세션과 무관한 기존 미커밋 변경(.gitignore, app.py, engine_adapter.py, scanner.html의 기존 변경) 포함 금지 — 단 scanner.html은 verdict 컨테이너 추가분만 hunk 단위로 스테이징 (`git apply --cached` 패치 방식, pathspec 커밋 금지)
- 커밋은 하되 푸시는 하지 말 것

## Out of Scope (후속)
- 노무라 점수 중복 표기 정리, 빈 TK Score 카드 정리
- 판정 룰의 백엔드 이관/서버 캐시
