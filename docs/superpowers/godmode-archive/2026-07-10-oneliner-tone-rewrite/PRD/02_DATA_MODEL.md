# 한줄평 엔진 톤 통일 리라이트 — 데이터 모델

> 이 작업은 새 데이터 필드나 API를 추가하지 않습니다.
> 기존 `_PHRASES` 딕셔너리 구조를 그대로 쓰고, 그 안의 문구 "내용"만 교체합니다.

---

## 전체 구조

```
_PHRASES: dict[버킷명(18종) -> list[문구 str]]

get_one_liner(d)
  → _bucket(d)                      # 버킷 결정(18종) — 이번 작업에서 불변
  → _PHRASES[bucket]                # 문구 풀 — 이번 작업의 대상
  → 해시 기반 선택(티커+버킷+지표)   # 이번 작업에서 불변
  → 문구 1개 반환
```

---

## 버킷 목록 (18종, 그룹별)

| 그룹(V2 모듈 경계) | 버킷 |
|---|---|
| negative | VALUE_TRAP, BUBBLE, OVERBOUGHT, FALLING_KNIFE, AVOID |
| positive_a | TRUE_VALUE, EXPENSIVE_JUSTIFIED, MOMENTUM_LEADER, BREAKOUT |
| positive_b | SLEEPING_GIANT, CASH_COW, SECTOR_LEADER, DEFENSIVE |
| mixed | EARNINGS_BEAT, STORY_STOCK, OVERSOLD, NEUTRAL, STRONG_BUY |

---

## 문구(phrase) 필드 (개념적 — 실제로는 리스트 안 문자열 하나)

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| bucket | 소속 버킷 | TRUE_VALUE | O |
| text | 문구 본문(리라이트 대상) | "이 실적에 이 가격이면 시장이 눈 감고 있는 거 맞음 ㄹㅇ" | O |
| origin | 원래 세대(코드상 구분 안 됨, 작업 추적용 개념) | base / V1 / V2 / V3 / V4 / MEME | X(비영속) |

### 관계
- 버킷 1개에 문구 여러 개(1:N) — 현재 버킷당 111~208개.
- `origin`은 실제 코드에 저장되는 필드가 아니다 — 현재 `_PHRASES`는 이미 병합 완료된 단일 리스트이므로, 리라이트 작업 시 "어느 원본 세대에서 왔는지"는 소스 모듈 파일(`_SPICY_ADDITIONS`, `_SPICY_V2_*`, `_SPICY_V3_ADDITIONS`, `_SPICY_V4_ADDITIONS`, `_MEME_ADDITIONS`) 각각을 리라이트 대상으로 순회하는 방식으로 추적한다.

---

## 왜 이 구조인가

- **확장성**: 문구 리스트 구조는 그대로이므로, 리라이트 후에도 향후 Phase 2(노출 데이터 기반 미세 교체)에서 동일한 구조로 개별 문구만 다시 바꿀 수 있다.
- **단순성**: 버킷 분류·선택 로직을 건드리지 않아, 리라이트가 실패하거나 롤백이 필요해도 시스템 동작에 영향이 없다(문구 텍스트 파일만 되돌리면 됨).

---

## [NEEDS CLARIFICATION]

- 없음(신규 데이터 없이 기존 구조만 재사용하기로 확정됨).
