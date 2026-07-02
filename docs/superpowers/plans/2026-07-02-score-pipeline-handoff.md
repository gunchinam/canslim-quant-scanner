# 인수인계서 — 점수 파이프라인 수정·재구축·검증·종가베팅 (2026-07-02)

## 현재 상태

**HEAD: `e786ccc`** (main 브랜치, 커밋 직접 진행 — 이 리포 관행)
**플랜: `docs/superpowers/plans/2026-07-02-score-pipeline-fixes.md`** (13개 태스크)
**진행 방식: superpowers:subagent-driven-development** — 태스크별 구현자 → 리뷰어 → 원장 기록
**원장: `.superpowers/sdd/progress.md`** (git-ignored 로컬 파일, 태스크 완료 기록 — 세션 재개 시 최우선 확인)

## 완료된 태스크 (1~9) — 전부 review Approved, 커밋 존재

| Task | 내용 | 커밋 범위 | 비고 |
|---|---|---|---|
| 1 | 드로다운 게이트 무효화 수정 (5전략 루프에 MDD 감쇄) | 63dc4ed→228a254 | |
| 2 | MoatBonus 멱등화 (`_MoatApplied` 마커) | 228a254→d645388 | Minor: `_MoatApplied` API 노출(기존 패턴과 동일, 문제없음) |
| 3 | midcap_alpha moat 이중반영 제거 | d645388→541ddcc | |
| 4 | 슈퍼그로스 승수 명명 상수화 | 541ddcc→9ba11e2 | 순수 리팩터링 |
| 5 | 스테일 캐시 점수 감쇄 (`_apply_stale_penalty`) | 9ba11e2→9258de8 | 구현자 API 스톨로 보고서 유실 → 컨트롤러가 직접 재작성 |
| 6 | `_Factors`/`RiskFlags` 기록 (quant_nexus_v20.py) | 9258de8→ebef149 | |
| 7 | `web_app/score_v2.py` 횡단면 표준화 모듈 | ebef149→2e54422 | 브리프의 `cap - 0.1` 버그를 구현자가 `cap`으로 정정(의도 부합, 채택) |
| 8 | scan_all/scan_sector에 ScoreV2 연결 | 2e54422→56396d8 | 구현자 세션 한도로 중단 → 컨트롤러가 diff 직접 검증 후 커밋 |
| 9 | 스냅샷에 factors/legacy/flags 기록 | 56396d8→c05e64d | ⚠️항목(기존 5개 테스트 컬렉션 에러)은 `git diff --stat 63dc4ed..HEAD`로 무관함 확인 완료 |

**전체 테스트**: `python -m pytest tests/test_score_fixes.py tests/test_score_v2.py tests/test_ablation.py -q` → 통과 확인됨(각 태스크 시점).

## 진행 중 — 재개 시 여기부터

**Task 10 (`score_ablation.py` forward IC CLI)**: 구현·커밋 완료(`e786ccc`), 테스트 3/3 PASS 확인됨. **리뷰가 아직 판정 미확보 상태로 중단됨** — 검토자 에이전트(`af6653c0de499023e`)에게 결과 전문을 두 차례 요청했으나 세션이 끝나 응답을 받지 못했다.

**재개 시 첫 액션**:
1. `SendMessage`로 `af6653c0de499023e`에 다시 결과를 요청하거나(응답이 없으면 세션 만료로 간주), 새 리뷰 에이전트를 투입해 재검토.
2. 리뷰 패키지는 이미 생성돼 있음: `.superpowers/sdd/review-c05e64d..e786ccc.diff`
3. 특히 확인할 것: `regime_ic.py`의 `_nw_tstat`/`_block_bootstrap_ci` 실제 시그니처와 `score_ablation.py` 호출부 정합성 — 구현자는 "브리프 예시와 정확히 일치, 조정 불필요"라 주장(`task-10-report.md`), 리뷰어가 직접 대조 검증하도록 지시했으나 결과 미회수.
4. 승인되면 원장에 `Task 10: complete (commits c05e64d..e786ccc, review Approved, 3/3 tests)` 한 줄 추가.

## 남은 태스크 (11~13)

브리프는 모두 `.superpowers/sdd/task-{N}-brief.md`로 이미 추출되어 있음(재추출 불필요).

- **Task 11**: `web_app/macro.py` 종가베팅 leading signal market-aware 개편 (미 지수선물 ES=F/NQ=F 추가, SKEW 판정 제외, KR/US 분기)
- **Task 12**: `/api/macro` market 파라미터 + 프론트(`app.js`) 연결
- **Task 13**: 통합 확인(전체 테스트 재실행, 구문/임포트 스모크, 실데이터 눈검증) + `git push`

## 재개 절차 (subagent-driven-development 그대로)

각 태스크마다:
1. `scripts/task-brief`로 이미 추출된 `.superpowers/sdd/task-N-brief.md` 사용(재추출 불요, 이미 있음)
2. 구현자 에이전트 투입(model: haiku, 브리프 경로 + 전역 제약 + 보고서 경로 전달) — **최종 응답에 상태·커밋해시·테스트결과를 직접 포함하라고 반드시 명시할 것** (안 하면 요약만 반환하는 경우가 잦았음)
3. 완료 후 `scripts/review-package BASE HEAD`로 diff 생성
4. 리뷰어 에이전트 투입(model: sonnet) — **이것도 최종 응답에 지정 형식 직접 포함을 명시할 것**. 이번 세션에서 리뷰어가 "대기 중입니다"/"확인." 같은 빈 요약만 반환하는 경우가 매우 잦았다 — 그때마다 `SendMessage`로 같은 에이전트를 재개해 전문을 재요청하면 됨(새 에이전트를 새로 띄우지 말 것 — 컨텍스트 재사용).
5. 승인되면 `.superpowers/sdd/progress.md`에 한 줄 기록 후 다음 태스크로.

## 알아둘 것 (세션에서 겪은 이슈)

- **구현자 세션 한도**: Task 8에서 구현자가 API 세션 한도로 커밋 직전 중단됨. 이럴 때는 `git status`/`git diff`로 실제 변경분을 직접 확인 → diff가 브리프와 일치하면 컨트롤러가 테스트 실행 후 직접 커밋하면 됨(재작업 불필요).
- **구현자 API 스톨**: Task 5에서도 유사하게 응답 스트림이 끊겼으나 커밋 자체는 성공했음 — `git log`로 실제 커밋 존재 여부를 항상 먼저 확인할 것.
- **보고서 파일 오염**: `.superpowers/sdd/task-N-report.md`는 git-ignored라 이전 플랜의 잔재가 남아있는 경우가 있었음(Task 5, 6, 8에서 관측). 새 태스크 투입 전 해당 파일 내용이 무관한 것이면 컨트롤러가 직접 짧게 재작성해도 무방.
- **점수 체감 변화**: Task 6~8 배포 후 실제 KR 대형주 15종목으로 라이브 비교한 결과, 레거시 절대점수와 ScoreV2 백분위 순위가 크게 재배치됨을 확인함(예: 삼성전자 58.3→92.9, 카카오 15.3→0.0). 사용자에게 이미 보고 완료. `env SCORE_V2=0`으로 언제든 롤백 가능.
- **베이스라인 실패 5건**: `tests/test_deeptech_story.py`, `test_entry_status_extract.py`, `test_entry_status_regime_gate.py`, `test_entry_status_v2.py`, `test_oneliner_fixes.py`가 `one_liner` 모듈 임포트 에러로 컬렉션 자체가 실패함. 이 플랜의 범위(`63dc4ed..HEAD`)와 무관함을 `git diff --stat`으로 확인 완료 — 별도 이슈이니 이 플랜에서 고치지 말 것(스코프 아님).

## 최종 사용자 확인 필요 사항 (Task 13 이후)

- Phase D(종가베팅) 완료 후, 실 서버 기동 상태에서 KR/US 탭별 매크로 판정이 올바르게 갈리는지 브라우저 확인 권장(스펙 Phase D 검증 항목).
- 전체 플랜 완료 후 `git push` 필요 — 지금까지는 로컬 커밋만 존재.
