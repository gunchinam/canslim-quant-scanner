# 한줄평 엔진 톤 통일 리라이트 — Phase 분리 계획

> 한 번에 3449개를 다 바꾸려 하면 검증이 부실해진다.
> 회차(버킷 그룹)별로 나눠서 각각 "검증까지 끝난 리라이트"를 완성한다.

---

## Phase 1: MVP (이번 골 범위)

### 목표
18개 버킷 전체의 base/V1/V3/V4/밈 유래 문구가 V2 수준의 날것 슬랭 톤으로 통일되고, STRONG_BUY 버킷이 195개로 보강된다.

### 기능 (회차별 버킷 그룹 단위)
- [ ] negative 그룹 리라이트: VALUE_TRAP, BUBBLE, OVERBOUGHT, FALLING_KNIFE, AVOID
- [ ] positive_a 그룹 리라이트: TRUE_VALUE, EXPENSIVE_JUSTIFIED, MOMENTUM_LEADER, BREAKOUT
- [ ] positive_b 그룹 리라이트: SLEEPING_GIANT, CASH_COW, SECTOR_LEADER, DEFENSIVE
- [ ] mixed 그룹 리라이트: EARNINGS_BEAT, STORY_STOCK, OVERSOLD, NEUTRAL
- [ ] STRONG_BUY 리라이트 + 신규 84개 보강(111→195개)
- [ ] 그룹마다 자동 검증(금지어/중복/규칙) + 무작위 표본 육안 검수

### 데이터
- 신규 없음. `02_DATA_MODEL.md`의 `_PHRASES` 구조를 그대로 사용.

### 인증
- 해당 없음.

### "진짜 제품" 체크리스트
- [ ] 실제 `one_liner.py`와 4개 `_spicy_v2_*.py` 모듈 및 base/V1/V3/V4/밈 정의부에 직접 반영(임시 목업 X)
- [ ] `tests/test_one_liner_consistency.py` 등 기존 테스트 스위트로 검증(수작업 확인만으로 완료 처리 X)
- [ ] 버킷마다 무작위 표본 육안 검수 기록

### Phase 1 시작 프롬프트
```
이 PRD를 읽고 Phase 1을 구현해주세요.
@PRD/01_PRD.md
@PRD/02_DATA_MODEL.md
@PRD/04_PROJECT_SPEC.md

Phase 1 범위(회차별 버킷 그룹 순서):
1. negative 그룹 (VALUE_TRAP, BUBBLE, OVERBOUGHT, FALLING_KNIFE, AVOID)
2. positive_a 그룹 (TRUE_VALUE, EXPENSIVE_JUSTIFIED, MOMENTUM_LEADER, BREAKOUT)
3. positive_b 그룹 (SLEEPING_GIANT, CASH_COW, SECTOR_LEADER, DEFENSIVE)
4. mixed 그룹 (EARNINGS_BEAT, STORY_STOCK, OVERSOLD, NEUTRAL)
5. STRONG_BUY (리라이트 + 84개 신규 보강)

반드시 지켜야 할 것:
- 04_PROJECT_SPEC.md의 "절대 하지 마" 목록 준수
- _bucket()/_raw_bucket()/get_one_liner() 로직 변경 금지 — 문구 텍스트만 교체
- 각 버킷 문구 개수·폴라리티 유지(STRONG_BUY만 195개로 증가)
- 그룹 완료마다 pytest 실행 + 무작위 표본 검수
```

---

## Phase 2: 확장 (다음 라운드 후보)

### 전제 조건
- Phase 1이 병합되어 실제 서비스에 반영된 상태.

### 목표
리라이트된 문구 중 실사용 노출 데이터를 바탕으로 반응이 약한 문구를 교체한다.

### 기능
- [ ] 실사용 노출 데이터 기반 문구 미세 교체

### 추가 데이터
- 노출/클릭 데이터 수집 방식은 이번 PRD 범위 밖 — 착수 시 별도 조사 필요.

### 통합 테스트
- Phase 1의 자동 검증 규칙이 여전히 통과하는지 확인.

---

## Phase 3: 고도화 (마지막, 별도 요청 시)

### 전제 조건
- Phase 1 + 2가 안정적으로 운영 중.

### 목표
세대 구분(base/V1/V2/V3/V4/밈) 자체를 없애고 단일 통합 파일로 정리하며, 검증된 톤을 다른 화면으로 확산한다.

### 기능
- [ ] base/V1/V2/V3/V4/밈 세대 구분을 단일 파일로 통합(기존 handover 문서의 미완 리팩터링 과제)
- [ ] `compare.html` 등 다른 화면의 문구에도 동일 톤 확산(별도 요청 시에만 착수)

### 주의사항
- 통합 리팩터링은 대규모 파일 변경이라 회귀 테스트 범위가 넓어짐 — 반드시 별도 PRD/골로 분리해 진행.

---

## Phase 로드맵 요약

| Phase | 핵심 기능 | 상태 |
|-------|----------|------|
| Phase 1 (MVP) | 18개 버킷 전체 V2 톤 리라이트 + STRONG_BUY 보강 | 시작 전 |
| Phase 2 | 노출 데이터 기반 문구 미세 교체 | Phase 1 완료 후 |
| Phase 3 | 세대 통합 리팩터링 + 타 화면 확산 | Phase 2 완료 후(별도 요청 시) |
