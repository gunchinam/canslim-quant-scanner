# 판단 포스터 한줄평 헤드라인 레이아웃 재설계 — VALIDATION

> PRD `01_PRD.md` §5 성공 기준을 검증 항목으로 변환. 각 항목은 실행 결과(스크린샷/커맨드 출력)로만 통과 처리한다 — 느낌으로 통과 금지.

- [x] V1. 모바일 `.dvp-word`가 40자 근접 한줄평에서도 최소 18px 이상 폰트를 유지한다. — Playwright로 실측정. 풀 내 최장 문구(44자) 렌더링 시 20px, 짧은 문구(18자)는 29.8px. 전 구간 20px 이상, 요구치(18px) 대비 여유 확보. 스크린샷(`verdict_extreme_mobile_long.png`, `_short.png`)으로 육안 확인.
- [x] V2. 데스크톱 `.dhb-word`가 40자 근접 한줄평에서도 모바일과 같거나 더 큰 최소 폰트를 유지한다. — 동일 조건 실측정 결과 44자 22px(모바일 20px 대비 큼), 18자 32px(모바일 29.8px 대비 큼). 4개 샘플 티커(NVDA/TSLA/AAPL/MSFT) 전부 데스크톱 폰트가 모바일보다 크거나 같음 확인.
- [x] V3. 두 레이아웃 모두 2~3줄 이내로 자연스럽게 줄바꿈되고, 레이아웃 붕괴·텍스트 잘림·가로 스크롤이 없다. — `scrollWidth/scrollHeight` 기반 오버플로 플래그 전부 `false`(44자 극단값 포함 8개 케이스). 스크린샷 4장(모바일/데스크톱 × 짧은/긴 문구)에서 2줄 줄바꿈, 확신도 배지·메타 셀과 겹침 없음 육안 확인.
- [x] V4. 배경색(`_pgCls`)·확신도%(`conv`)·`_pvReason`(3줄 이유)·신호등 라벨이 변경 전과 동일하게 동작한다. — `git diff web_app/static/app.js` 결과 `_dvpWordPx`/`_dhbWordPx` 계산식 2줄과 주석만 변경, `_pgCls`/`conv`/`_pvReason` 계산 블록은 diff에 없음(미변경). 스크린샷에서도 확신도%·배경 그라디언트·이유 텍스트 정상 표시 확인.
- [x] V5. `tests/test_one_liner_consistency.py`가 기존 베이스라인(2 failed/24 passed)과 동일하게 유지된다. — 재실행 결과 2 failed/24 passed(동일), 실패 2건은 `_bucket()` 분류 로직 기존 결함으로 이번 변경과 무관.
- [x] V6. `web_app/tests/`(`test_history_timeline.py` 제외)가 195 passed 베이스라인과 동일하게 유지된다. — 재실행 결과 195 passed(동일).

## blocking 가정

- 없음.
