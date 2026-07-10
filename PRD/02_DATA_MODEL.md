# 판단 포스터 한줄평 연결 + 명사형 종결 재정비 — 데이터 모델

> 새 데이터 필드나 API를 추가하지 않습니다.
> 기존 `d.OneLiner`(API 응답)를 판단 포스터에 연결하고, 기존 `_PHRASES` 구조는 그대로 쓰면서 문구 문자열의 종결어미만 국소 교정합니다.

---

## 전체 구조

```
API 응답 d (종목 dict, JSON)
  ├─ d.OneLiner        (이미 존재 — one_liner.py의 annotate()가 채움)
  │    └─ app.js _renderEntryVerdict(d)에서 헤드라인(_pvWord 자리)에 이 값을 그대로 사용
  ├─ d.BFScore / d.EntryScore / d.TotalScore / d.GreedZone / d.EntryPlan
  │    └─ conv(진입 타이밍 확신도) 계산용 — 이번 작업에서 미변경
  └─ ...(기존 필드 다수, 미변경)

one_liner.py _PHRASES: dict[버킷명(18종) -> list[문구 str]]
  각 문구 문자열의 "종결어미"만 국소 교정(명사형 전성어미로)
  → 의미·버킷 소속·문구 개수·극성(긍정/부정/중립)은 리라이트 전과 완전히 동일하게 유지
```

---

## 컴포넌트별 상세

### 판단 포스터 (`dp-verdict-poster` / `dp-hero-banner-dt`)

| 요소 | 데이터 소스 | 변경 여부 |
|------|------|------|
| 헤드라인(`dvp-word`/`dhb-word`) | ~~`_pvWord`(15단계×5개 고정 픽)~~ → `d.OneLiner` | **변경** |
| 3줄 이유(`dvp-reason`/`dhb-reason`) | `_pvReason`(15단계×4개 고정 픽) | 미변경 |
| 배경 클래스/신호등(`_pgCls`) | `conv` 기반 4단계(진입 유리/관심 구간/관망/보류) | 미변경 |
| 확신도 %(`dvp-conf-num`) | `conv`(0-100) | 미변경 |
| 배경 라벨(`dvp-bg`/`_pvBg`) | `_pvBg`(15단계×3개 고정 픽) | 미변경 |

### 한줄평 문구 풀 (`_PHRASES`)

| 필드 | 설명 | 예시(재정비 전 → 후) | 필수 |
|------|------|------|------|
| bucket | 소속 버킷(18종, 불변) | VALUE_TRAP | O |
| text | 문구 본문 — 종결어미만 교정 | "이거 사면 주갤에서 조리돌림 당하는 거 아님?" → "이거 사면 주갤에서 조리돌림 당함" | O |

### 관계
- `d.OneLiner`는 종목 1개당 1개 값(해시 기반으로 `_PHRASES[bucket]`에서 이미 선택된 결과) — 판단 포스터와 `hero-oneliner`(detail.html)가 같은 값을 참조하게 됨(단, 이번 범위는 판단 포스터 헤드라인만).
- `_PHRASES` 구조 자체(딕셔너리 키/리스트 개수)는 불변 — 리스트 안 문자열만 국소 치환.

---

## 왜 이 구조인가

- **확장성**: `d.OneLiner`를 그대로 재사용하므로, 향후 Phase 2(`_pvReason` 톤 정비)나 Phase 3(판단 체계 통합)에서도 같은 필드를 계속 활용 가능.
- **단순성**: 새 API 필드나 데이터 흐름 변경이 없어, 백엔드(`app.py`)는 전혀 건드리지 않는다 — 프론트(`app.js`+CSS)와 문구 콘텐츠(`one_liner.py`)만 수정.

---

## [NEEDS CLARIFICATION]

- 없음(신규 데이터 없이 기존 필드만 재사용하기로 확정됨).
