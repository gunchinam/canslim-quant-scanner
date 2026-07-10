# 종목 상세 드로워 재설계 — 프로젝트 스펙

> AI가 코드를 짤 때 지켜야 할 규칙과 절대 하면 안 되는 것.
> 이 문서를 AI에게 항상 함께 공유하세요.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Flask (기존) | 이미 운영 중인 백엔드, 변경 대상 아님 |
| 템플릿 | Jinja2 (기존) | `web_app/templates/detail.html`이 이미 Jinja2 템플릿 |
| 스타일링 | 순수 CSS(인라인 `<style>` 블록, 기존) | `detail.html` 내부에 이미 인라인 스타일 블록이 있고, 공용 토큰은 `web_app/static/theme.css`에서 가져옴. 새 CSS 프레임워크 도입 없음 |
| 색 토큰 | `theme.css`의 `--brand-soft`, `--surface-subtle`, `--radius`, `--shadow-card` 등 기존 토큰만 재사용 | 1차 라운드에서 이미 검증된 토큰, 새 hex 값 발명 금지 |
| 테스트 | pytest(`web_app/tests/`) | 기존 회귀 테스트 스위트 |

---

## 프로젝트 구조 (관련 부분만)

```
종목스캐너/
├── web_app/
│   ├── app.py                      # Flask 서버 (수정 대상 아님)
│   ├── engine_adapter.py           # 데이터 어댑터 (수정 대상 아님)
│   ├── templates/
│   │   ├── detail.html             # 이번 작업의 유일한 수정 대상
│   │   └── scanner.html            # 수정 대상 아님(Phase 3 후보)
│   ├── static/
│   │   └── theme.css               # 기존 토큰 읽기 전용(신규 토큰 추가 안 함)
│   └── tests/                      # pytest 회귀 테스트
└── PRD/                            # 이 문서들
```

---

## 절대 하지 마 (DO NOT)

> AI에게 코드를 시킬 때 이 목록을 반드시 함께 공유하세요.

- [ ] `web_app/templates/detail.html` 외의 파일(`scanner.html`, `app.py`, `engine_adapter.py` 등)을 수정하지 마
- [ ] `.hero-oneliner`, `dp-verdict-poster` 컴포넌트의 CSS/마크업을 건드리지 마(범위 완전 제외)
- [ ] CAN SLIM 리스트, 소유구조/내부자 카드, 재무 표 등 데이터 나열 카드의 배경색·구조를 바꾸지 마(흰 배경 유지)
- [ ] `theme.css`에 새 토큰이나 새 hex 색상 값을 추가하지 마 — `--brand-soft`, `--surface-subtle` 등 기존 토큰만 재사용
- [ ] 새 JS 라이브러리, CSS 프레임워크, 빌드 도구를 추가하지 마
- [ ] 새 데이터 필드나 API 엔드포인트를 추가하지 마 — 기존 DOM id(`detail-score`, `detail-price` 등)로 들어오는 값만 재배치
- [ ] 스크린샷으로 시각 검증 없이 레이아웃 변경을 "완료"로 보고하지 마

---

## 항상 해 (ALWAYS DO)

- [ ] 변경하기 전에 어떤 CSS/마크업을 바꿀지 계획을 먼저 보여줘
- [ ] 각 변경 단계마다 Flask 개발 서버를 띄워 스모크 테스트(`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:PORT/` → `200` 기대)
- [ ] 레이아웃이 바뀌는 변경은 Playwright 등으로 스크린샷을 찍어 육안 확인 후 임시 스크린샷 파일 삭제
- [ ] 데스크톱과 모바일(480px 기준) 두 뷰포트 모두 확인
- [ ] pytest 회귀 테스트를 돌려 통과 수가 작업 전과 동일한지 확인(기존 실패 건수는 베이스라인으로 취급, 더 늘면 회귀로 간주)
- [ ] 커밋은 태스크 단위로 작게 나눠서 진행

---

## 테스트 방법

```bash
# 로컬 실행 (포트는 비어있는 번호로 지정)
cd web_app && PORT=5061 python app.py

# 스모크 테스트
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5061/

# pytest 회귀
cd web_app && python -m pytest tests/ -q
```

---

## 배포 방법

- 해당 없음(이번 작업은 로컬 드로워 UI 변경이며, 기존 배포 파이프라인을 그대로 사용).

---

## 환경변수

- 해당 없음(이번 작업은 신규 환경변수를 필요로 하지 않음).

---

## [NEEDS CLARIFICATION]

- 없음.
