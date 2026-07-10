# 판단 포스터 한줄평 연결 + 명사형 종결 재정비 — Phase 분리 계획

> 헤드라인 연결(작지만 임팩트 큰 변경)과 3533개 문구 재정비(크지만 반복적인 변경)를 한 골 안에서 순서대로 처리한다.

---

## Phase 1: MVP (이번 골 범위)

### 목표
판단 포스터 헤드라인에 진짜 한줄평이 뜨고, 모든 한줄평이 명사형 종결로 통일된다.

### 기능
- [ ] `app.js`의 `_renderEntryVerdict`에서 헤드라인 픽 로직(`_pvWord`)을 `d.OneLiner`로 교체(`dp-verdict-poster`, `dp-hero-banner-dt` 둘 다)
- [ ] `dvp-word`/`dhb-word` CSS에 `font-size: clamp(...)` 적용
- [ ] 18개 버킷(negative 5 + positive_a 4 + positive_b 4 + mixed 4 + STRONG_BUY 1) 3533개 문구 종결어미를 명사형으로 국소 재정비 — 버킷 그룹 단위 회차 진행(직전 골과 동일한 그룹 경계 재사용)
- [ ] 반영 후 회귀 검증(개수·중복·`tests/test_one_liner_consistency.py`·`web_app/tests/` 전체·표본 육안)

### 데이터
- 신규 없음. `02_DATA_MODEL.md`의 `d.OneLiner` + `_PHRASES` 구조를 그대로 사용.

### 인증
- 해당 없음.

### "진짜 제품" 체크리스트
- [ ] 실제 Flask 개발 서버로 스캐너 목록 → 드로워 → 판단 포스터까지 실사용 흐름으로 확인(정적 목업 X)
- [ ] 데스크톱 + 모바일 두 뷰포트에서 긴 한줄평이 헤드라인에 깨짐 없이 표시되는지 스크린샷 검증
- [ ] 기존 pytest 회귀 테스트 통과 수 유지

### Phase 1 시작 프롬프트
```
이 PRD를 읽고 Phase 1을 구현해주세요.
@PRD/01_PRD.md
@PRD/02_DATA_MODEL.md
@PRD/04_PROJECT_SPEC.md

Phase 1 범위:
1. app.js _renderEntryVerdict의 _pvWord 자리를 d.OneLiner로 교체(dp-verdict-poster, dp-hero-banner-dt 둘 다)
2. dvp-word/dhb-word CSS font-size clamp() 적용
3. 18개 버킷 문구 종결어미 명사형 재정비(버킷 그룹별 회차)
4. 반영 후 회귀 검증

반드시 지켜야 할 것:
- 04_PROJECT_SPEC.md의 "절대 하지 마" 목록 준수
- _pvReason/conv 계산/배경색 로직은 건드리지 않음
- _PHRASES 개수·버킷·극성 불변, 문구 문자열의 종결어미만 교정
- 실제 화면(스캐너 드로워)에서 스크린샷으로 헤드라인 표시 확인
```

---

## Phase 2: 확장 (다음 라운드 후보)

### 전제 조건
- Phase 1이 병합되어 실제 화면에 반영된 상태.

### 목표
판단 포스터의 3줄 이유 설명도 한줄평 톤에 맞춰 다듬고, drawer 전체의 톤 일관성을 점검한다.

### 기능
- [ ] `_pvReason`(3줄 이유 설명) 문체를 한줄평 톤에 맞춰 다듬기
- [ ] `detail.html`의 `hero-oneliner`와 판단 포스터 간 톤 일관성 점검

### 추가 데이터
- 없음.

### 통합 테스트
- Phase 1 기능(헤드라인 연결, CSS clamp, 명사형 재정비)이 여전히 정상 동작하는지 확인.

---

## Phase 3: 고도화 (마지막, 별도 요청 시)

### 전제 조건
- Phase 1 + 2가 안정적으로 운영 중.

### 목표
진입 타이밍(conv)과 종목 성격(한줄평) 두 축을 하나의 판단 체계로 통합 재설계한다.

### 기능
- [ ] conv와 한줄평을 통합한 새 판단 체계 재설계(별도 요청 시에만 착수)

### 주의사항
- 두 축을 통합하려면 `conv` 계산 로직과 `_bucket()` 로직을 함께 재검토해야 하므로 대규모 변경 — 반드시 별도 PRD/골로 분리해 진행.

---

## Phase 로드맵 요약

| Phase | 핵심 기능 | 상태 |
|-------|----------|------|
| Phase 1 (MVP) | 헤드라인 연결 + CSS + 3533개 명사형 재정비 + 회귀 검증 | 시작 전 |
| Phase 2 | `_pvReason` 톤 정비 + 드로워 톤 일관성 점검 | Phase 1 완료 후 |
| Phase 3 | conv+한줄평 통합 판단 체계 재설계 | Phase 2 완료 후(별도 요청 시) |
