# 한줄평 엔진 톤 통일 리라이트 — 프로젝트 스펙

> AI가 코드를 짤 때 지켜야 할 규칙과 절대 하면 안 되는 것.
> 이 문서를 AI에게 항상 함께 공유하세요.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 언어 | 순수 Python(기존) | `web_app/one_liner.py`와 `_spicy_v2_*.py` 4개 모듈이 이미 이 구조 |
| 데이터 구조 | `dict[str, list[str]]`(기존) | 버킷별 문구 리스트, 새 구조 도입 없음 |
| 테스트 | pytest(`tests/test_one_liner_consistency.py` 등) | 기존 톤/규칙 검증 스위트 |

---

## 프로젝트 구조 (관련 부분만)

```
종목스캐너/
├── web_app/
│   ├── one_liner.py               # 이번 작업의 핵심 대상
│   │                               #   base _PHRASES, _SPICY_ADDITIONS(V1),
│   │                               #   _MEME_ADDITIONS, _SPICY_V3_ADDITIONS,
│   │                               #   _SPICY_V4_ADDITIONS 정의부 + 병합 루프
│   ├── _spicy_v2_negative.py      # V2 negative 모듈(리라이트 톤 기준)
│   ├── _spicy_v2_positive_a.py    # V2 positive_a 모듈(리라이트 톤 기준)
│   ├── _spicy_v2_positive_b.py    # V2 positive_b 모듈(리라이트 톤 기준)
│   └── _spicy_v2_mixed.py         # V2 mixed 모듈(리라이트 톤 기준)
├── tests/
│   └── test_one_liner_consistency.py  # 톤/규칙 회귀 테스트
└── docs/
    └── handover-jugal-tone.md     # 기존 톤 가이드 인수인계서(참고용)
```

---

## 절대 하지 마 (DO NOT)

> AI에게 코드를 시킬 때 이 목록을 반드시 함께 공유하세요.

- [ ] `_bucket()`, `_raw_bucket()`, `_score_grade()` 등 버킷 분류/등급 로직을 변경하지 마
- [ ] `get_one_liner()`, `_friendly_one_liner()`의 해시 기반 선택 알고리즘을 변경하지 마
- [ ] 리라이트 대상이 아닌 파일(`web_app/app.py`, `web_app/engine_adapter.py`, 템플릿 파일 등)을 수정하지 마
- [ ] 격식체(습니다/합니다/입니다)를 쓰지 마
- [ ] 기술용어(RSI/PER/PBR/신저가/과매도/시그널 등, `tests/test_one_liner_consistency.py`의 `_FORBIDDEN_TECH` 패턴 참고)를 쓰지 마
- [ ] 숫자나 마침표를 문구에 넣지 마
- [ ] NEUTRAL 버킷에 방향성 명령(사라/팔아라/오를 거/빠질 거)을 쓰지 마
- [ ] 리라이트 후 버킷별 문구 개수나 폴라리티(긍정/부정/중립)를 원본과 다르게 바꾸지 마(STRONG_BUY만 195개로 증가 예외)
- [ ] pytest 실행/표본 검수 없이 리라이트를 "완료"로 보고하지 마

---

## 항상 해 (ALWAYS DO)

- [ ] 버킷 그룹(negative → positive_a → positive_b → mixed → STRONG_BUY) 순서로 작업하고, 그룹마다 pytest 실행
- [ ] 리라이트 시 V2 톤 가이드 참고: 나뚜믄오른다/존버/물타기/깡통/호구/떡상·떡락/개미/뇌동매매/주린이/ㄹㅇ/ㅋㅋ, "10년차 개미 고인물이 후배한테 한마디 던지는 느낌"
- [ ] 극성 일치 유지: 긍정 버킷에 자조 밈 금지, 부정 버킷에 확신 톤 금지(`docs/handover-jugal-tone.md` §톤 가이드 참고)
- [ ] 원문의 핵심 의미(예: "저평가", "과열", "실적 서프라이즈")는 유지하고 표현만 슬랭화
- [ ] 그룹 완료마다 무작위 5~10개 표본을 육안으로 확인
- [ ] 커밋은 그룹 단위로 작게 나눠서 진행

---

## 테스트 방법

```bash
# 한줄평 관련 테스트만 실행
cd web_app && python -m pytest ../tests/test_one_liner_consistency.py -q

# 전체 회귀 테스트
cd web_app && python -m pytest tests/ -q
```

---

## 배포 방법

- 해당 없음(정적 문구 풀 변경이며, 기존 배포 파이프라인을 그대로 사용).

---

## 환경변수

- 해당 없음.

---

## [NEEDS CLARIFICATION]

- 없음.
