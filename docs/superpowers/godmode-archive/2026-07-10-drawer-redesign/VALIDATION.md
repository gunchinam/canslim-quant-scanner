# 종목 상세 드로워 재설계 — VALIDATION

> PRD `01_PRD.md` §5 성공 기준을 검증 항목으로 변환. 각 항목은 실행 결과(스크린샷/커맨드 출력)로만 통과 처리한다 — 느낌으로 통과 금지.

- [x] V1. 히어로 카드 안에서 "결론(점수·등급·한줄평)"과 "근거(현재가·RSI·목표가)"가 배경색/여백/타이포그래피로 시각적으로 구분된다. — `.hero-evidence`(surface-subtle 박스)로 RSI·스파크라인·현재가·목표가를 결론(점수·등급) 아래 별도 패널로 분리. `/detail/INCY` 데스크톱·모바일 스크린샷으로 육안 확인 완료.
- [x] V2. 히어로/실적/컨센서스/투자자동향 카드가 개별 흰 카드로 따로 떠 보이지 않고, 섹션 라벨 밴드로 하나의 흐름처럼 연결되어 보인다. — 실적 한눈에·컨센서스·투자자동향 헤더에 `--surface-subtle` 밴드 통일 적용. 스크린샷으로 확인 완료.
- [x] V3. 탭 네비게이션에서 활성 탭이 비활성 탭과 명확히 구분된다. — active 탭에 `font-weight:700` + `background:var(--surface-subtle)` + border-bottom 3px 적용. 스크린샷에서 CAN SLIM 탭 강조 확인.
- [x] V4. 목표가 박스와 컨센서스 박스가 `--brand-soft` 톤으로 강조되어 보인다. — grep으로 `detail.html:1161`(목표가 박스), `:1201`(컨센서스 박스) 두 곳에 `background:var(--brand-soft)` 적용 확인 + 스크린샷 육안 확인.
- [x] V5. 데스크톱(900px)과 모바일(480px) 두 뷰포트 스크린샷에서 레이아웃 깨짐(텍스트 겹침, 카드 잘림, 가로 스크롤)이 없다. — Playwright로 `/detail/INCY` 두 뷰포트 풀페이지 스크린샷 촬영, 육안 확인 완료(겹침·잘림 없음).
- [x] V6. 기존 pytest 회귀 테스트가 변경 전과 동일한 통과 수를 유지한다. — `cd web_app && python -m pytest tests/ -q` → `195 passed, 10 failed`. 실패 10건은 2026-07-08 플랜 문서에 기록된 기존 베이스라인(`test_history_timeline.py`, `test_chat_client_fallback.py`)과 완전히 일치, 이번 작업과 무관.

- [x] V7. 정보값 없는 히어로 장식 문구("🏆 이 회사 자체는 좋은가?" 라벨, hero-grade-dot, hero-watermark), 점수 추세 스파크라인(score-sparkline-wrap), 실적/컨센서스 카드의 중복 보조 안내 문구("자세히는 재무 지표 탭", cs-summary)가 마크업에서 제거된다. — grep으로 6개 요소 마크업 삭제 확인 + 관련 미사용 CSS(`.hero-grade-dot`, `.hero-watermark`, `.cs-summary`, `.cs-summary-text`) 삭제 확인. app.js의 관련 함수(`loadScoreSparkline`, cs-summary 렌더 코드)는 모두 `if (!el) return` 가드가 있어 마크업 제거 후에도 안전하게 no-op됨(app.js는 프로젝트 스펙에 따라 수정하지 않음). `/detail/INCY` 데스크톱·모바일 스크린샷으로 육안 확인 완료.

## blocking 가정

- 없음 (PRD §7 [NEEDS CLARIFICATION]의 두 항목은 구현 단계에서 시안 비교로 스스로 해소 가능한 non-blocking 항목으로 판단됨).
