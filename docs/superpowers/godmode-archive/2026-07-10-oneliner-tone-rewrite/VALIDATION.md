# 한줄평 엔진 톤 통일 리라이트 — VALIDATION

> PRD `01_PRD.md` §5 성공 기준을 검증 항목으로 변환. 각 항목은 실행 결과(pytest/스크립트 출력/표본 검수 기록)로만 통과 처리한다 — 느낌으로 통과 금지.

## 그룹별 리라이트 완료 (Phase 1)

- [x] V1. negative 그룹(VALUE_TRAP, BUBBLE, OVERBOUGHT, FALLING_KNIFE, AVOID) — base/V1/V3/V4/MEME 유래 문구 790개를 V2 톤으로 리라이트. 딕셔너리 블록 단위 파싱·재조립 방식으로 반영(문자열 전역 치환 방식은 교차 오염 버그가 있어 폐기, 자세한 경위는 LOOP.md 회차 기록 참고). 개수(208/206/199/198/202) 및 중복 0 확인. `tests/test_one_liner_consistency.py` 5개 실패는 전부 negative 그룹과 무관한 기존 버그(원본에서도 동일 실패, git stash A/B 비교로 확정).
- [x] V2. positive_a 그룹(TRUE_VALUE, EXPENSIVE_JUSTIFIED, MOMENTUM_LEADER, BREAKOUT) — 595개 리라이트 반영, 개수(203/187/206/196) 원본과 정확히 일치, 중복 0. 추가로 "V2 native는 이미 완성됐으니 안 건드린다"는 가정이 틀렸음을 발견 — V2 모듈 자체에 기술용어(PER/밸류/모멘텀/신고가/시총 등) 36건이 섞여 있어 4개 V2 모듈 파일에서 직접 수정(자세한 경위는 LOOP.md 참고). pytest offender에서 TRUE_VALUE/EXPENSIVE_JUSTIFIED/MOMENTUM_LEADER/BREAKOUT 완전히 사라짐 확인.
- [x] V3. positive_b 그룹(SLEEPING_GIANT, CASH_COW, SECTOR_LEADER, DEFENSIVE) — 562개 리라이트 반영, 개수(178/192/196/201) 원본과 정확히 일치, 중복 0. 세션 도중 fast-worker API 세션 한도 도달로 4개 에이전트 모두 실패(결과 부분 저장) → 오케스트레이터가 직접 부족분(CASH_COW 1개·SECTOR_LEADER 10개·DEFENSIVE 17개·SLEEPING_GIANT 116개 전체)을 작성해 완료. pytest offender에서 4개 버킷 완전히 사라짐, test_dividend 실패도 CASH_COW 리라이트로 자연 해소.
- [x] V4. mixed 그룹(EARNINGS_BEAT, STORY_STOCK, OVERSOLD, NEUTRAL) — 592개 리라이트 반영, 개수(196/181/193/196) 원본과 정확히 일치, 중복 0. 세션 한도 재발로 오케스트레이터가 STORY_STOCK 136개와 NEUTRAL 미처리분 16개를 직접 보강. NEUTRAL 리스트 안 인라인 주석 때문에 safe_apply.py 파서가 한 번 실패 → 주석 스킵 로직 추가해 해결. pytest 2 failed/24 passed로 개선(test_generic_pools_have_no_unverified_assertions, test_no_technical_jargon_anywhere 완전히 해소) — 남은 2개는 버킷분류 로직 기존 버그(리라이트 전부터 존재, 무관).
- [x] V5. STRONG_BUY — 기존 66개(리라이트 대상, V2 native 45개 제외) 리라이트 + 신규 84개(fast-worker 2세트, 교차 중복 0 확인) 보강으로 111→195개 도달. 중복 0.

## 구조/로직 불변성

- [x] V6. 리라이트 전후로 각 버킷의 문구 "개수"가 STRONG_BUY(111→195) 외에는 전부 원본과 정확히 일치(18개 버킷 전수 확인, 총계 3449→3533으로 +84만 증가).
- [x] V7. `_bucket()`, `_raw_bucket()`, `get_one_liner()`, `_friendly_one_liner()` 함수 본문이 git diff에 전혀 나타나지 않음 — 변경 없음 확인.

## 품질 검증

- [x] V8. `tests/test_one_liner_consistency.py` — 5 failed(negative 반영 직후) → 2 failed/24 passed(전 그룹 반영 후, `test_generic_pools_have_no_unverified_assertions`·`test_no_technical_jargon_anywhere`·`test_dividend_phrase_not_in_general_pool` 완전 해소). 남은 2개(`test_consistency_cases`, `_UT::test_all`)는 리라이트 전 원본에서도 동일하게 실패하는 버킷분류 로직 기존 버그(git stash A/B 비교로 확정) — 이번 작업과 무관.
- [x] V9. `web_app/tests/` 전체 회귀 195 passed/10 failed — 기존 베이스라인과 정확히 일치, 회귀 없음.
- [x] V10. 18개 버킷 전체 균등 표본(각 4개, 총 72개) 육안 검수 완료. 톤이 "ㄹㅇ/ㅇㅈ/ㅋㅋ/국룰/줍줍/떡상·떡락/이불킥" 등 V2 슬랭으로 일관되게 통일됨, 버킷별 극성(긍정/부정/중립) 유지 확인.

## blocking 가정

- 없음.
