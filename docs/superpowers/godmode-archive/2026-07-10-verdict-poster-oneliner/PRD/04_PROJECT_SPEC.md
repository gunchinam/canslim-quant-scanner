# 판단 포스터 한줄평 연결 + 명사형 종결 재정비 — 프로젝트 스펙

> AI가 코드를 짤 때 지켜야 할 규칙과 절대 하면 안 되는 것.
> 이 문서를 AI에게 항상 함께 공유하세요.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 언어 | 순수 Python(기존) | `web_app/one_liner.py`와 4개 V2 모듈 |
| 프론트 | 순수 JS(기존) | `web_app/static/app.js`의 `_renderEntryVerdict` |
| 스타일링 | 순수 CSS(기존) | `dvp-word`/`dhb-word` 클래스에 `clamp()` 추가 |
| 테스트 | pytest(`tests/test_one_liner_consistency.py`, `web_app/tests/`) | 기존 회귀 테스트 스위트 |

---

## 프로젝트 구조 (관련 부분만)

```
종목스캐너/
├── web_app/
│   ├── one_liner.py                   # 문구 종결어미 재정비 대상
│   ├── _spicy_v2_negative.py          # 필요시 종결어미 재정비 대상
│   ├── _spicy_v2_positive_a.py        # 필요시 종결어미 재정비 대상
│   ├── _spicy_v2_positive_b.py        # 필요시 종결어미 재정비 대상(신규 파일일 수 있음, 확인 필요)
│   ├── _spicy_v2_mixed.py             # 필요시 종결어미 재정비 대상
│   ├── static/
│   │   └── app.js                     # _renderEntryVerdict 수정 대상(헤드라인 로직 + CSS 인접부)
│   ├── templates/
│   │   ├── scanner.html               # dp-verdict-poster 마크업(수정 대상 아님, 확인만)
│   │   └── detail.html                # hero-oneliner(이번 범위 밖, 건드리지 않음)
│   └── tests/                         # pytest 회귀 테스트
└── PRD/                                # 이 문서들
```

---

## 절대 하지 마 (DO NOT)

> AI에게 코드를 시킬 때 이 목록을 반드시 함께 공유하세요.

- [ ] `_renderEntryVerdict`의 `conv` 계산 로직(BFScore/EntryScore/TotalScore/GreedZone/MDD 가중치)을 변경하지 마
- [ ] `_pvReason`(3줄 이유), `_pgCls`(배경 신호등 클래스), `_pvBg`(배경 라벨) 로직을 변경하지 마 — 이번 범위는 헤드라인(`_pvWord` 자리)뿐
- [ ] `_bucket()`, `_raw_bucket()`, `get_one_liner()` 등 한줄평 선택 로직을 변경하지 마 — 문구 "텍스트"만 국소 교정
- [ ] `_PHRASES`의 버킷 개수, 문구 개수, 각 문구의 극성(긍정/부정/중립)을 바꾸지 마
- [ ] 격식체(습니다/합니다/입니다), 기술용어(RSI/PER/PBR 등), 숫자, 마침표를 새로 넣지 마(직전 골에서 이미 검증된 규칙 유지)
- [ ] `detail.html`의 `hero-oneliner`, `dp-verdict-poster`(주갤 텍스처 카드) 마크업/CSS를 건드리지 마
- [ ] 새 API 필드나 백엔드 엔드포인트를 추가하지 마 — `d.OneLiner`가 이미 존재함
- [ ] 스크린샷으로 실제 화면 검증 없이 "완료"로 보고하지 마

---

## 항상 해 (ALWAYS DO)

- [ ] 헤드라인 연결(Phase 1의 1~2번)을 먼저 끝내고 스크린샷으로 확인한 뒤, 문구 재정비(3번)로 넘어가기
- [ ] 문구 재정비는 버킷 그룹 단위(negative/positive_a/positive_b/mixed/STRONG_BUY)로 나눠 회차 진행
- [ ] 각 회차마다 `tests/test_one_liner_consistency.py` 실행해 회귀 확인
- [ ] 데스크톱과 모바일 두 뷰포트 모두에서 헤드라인 표시 확인(긴 문구 잘림/줄바꿈 여부)
- [ ] "명사형 종결" 판단이 애매한 문구는 원문 의미를 최우선으로 보존하고, 억지로 어색하게 명사형으로 바꾸지 않기(자연스러운 명사형 어미가 없으면 원문 유지도 허용)
- [ ] 커밋은 단계 단위로 작게 나눠서 진행

---

## 테스트 방법

```bash
# 한줄평 관련 테스트만 실행
cd web_app && python -m pytest ../tests/test_one_liner_consistency.py -q

# 전체 회귀 테스트
cd web_app && python -m pytest tests/ -q

# 실제 화면 스모크 테스트
cd web_app && PORT=5061 python app.py
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5061/
```

---

## 배포 방법

- 해당 없음(로컬 UI/문구 변경이며, 기존 배포 파이프라인을 그대로 사용).

---

## 환경변수

- 해당 없음.

---

## [NEEDS CLARIFICATION]

- `_spicy_v2_positive_b.py` 파일이 실제로 존재하는지(직전 골에서 positive_b 그룹 리라이트 시 별도 V2 모듈 없이 base/V1/MEME/V3/V4만 있었을 수 있음) 구현 착수 시 확인 필요.
