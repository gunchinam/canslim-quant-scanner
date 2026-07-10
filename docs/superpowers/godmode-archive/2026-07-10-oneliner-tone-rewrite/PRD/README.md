# 한줄평 엔진 톤 통일 리라이트 — 디자인 문서

> Show Me The PRD로 생성됨 (2026-07-10)

## 문서 구성

| 문서 | 내용 | 언제 읽나 |
|------|------|----------|
| [01_PRD.md](./01_PRD.md) | 뭘 리라이트하는지, 왜, 성공 기준 | 작업 시작 전 |
| [02_DATA_MODEL.md](./02_DATA_MODEL.md) | `_PHRASES` 구조와 버킷 그룹 | 리라이트 순서 잡을 때 |
| [03_PHASES.md](./03_PHASES.md) | Phase 1(MVP)/2/3 단계별 계획 | 회차 순서 정할 때 |
| [04_PROJECT_SPEC.md](./04_PROJECT_SPEC.md) | AI가 지켜야 할 규칙(절대 하지 마 / 항상 해) | AI에게 코드를 시킬 때마다 |

## 다음 단계

Phase 1을 시작하려면 [03_PHASES.md](./03_PHASES.md)의 "Phase 1 시작 프롬프트"를 참고하세요.

이 PRD는 godmode 파이프라인의 스테이지 B(골 세팅)로 이어집니다. goaljaby 미설치 상태이므로, 이 세션에서 직접 VALIDATION.md/LOOP.md를 작성해 골 루프를 대행합니다(이전 드로워 재설계 골과 동일한 폴백 방식 — 그 골의 기록은 `docs/superpowers/godmode-archive/2026-07-10-drawer-redesign/`에 보관됨).

## 미결 사항

- 리라이트 중 원문 핵심 의미 유지 경계는 구현 단계에서 원문 대조로 판단.
- `_METRIC_PHRASES`/`_FLAVOR_PHRASES`/`_ACTION_HINTS`(보조 문구 풀)의 리라이트 포함 여부는 `_PHRASES`(메인 풀) 완료 후 판단.
