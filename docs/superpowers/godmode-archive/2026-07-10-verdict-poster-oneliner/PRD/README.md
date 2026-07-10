# 판단 포스터 한줄평 연결 + 명사형 종결 재정비 — 디자인 문서

> Show Me The PRD로 생성됨 (2026-07-10)

## 문서 구성

| 문서 | 내용 | 언제 읽나 |
|------|------|----------|
| [01_PRD.md](./01_PRD.md) | 뭘 연결·재정비하는지, 왜, 성공 기준 | 작업 시작 전 |
| [02_DATA_MODEL.md](./02_DATA_MODEL.md) | `d.OneLiner`와 `_PHRASES` 데이터 흐름 | 연결 로직 짤 때 |
| [03_PHASES.md](./03_PHASES.md) | Phase 1(MVP)/2/3 단계별 계획 | 작업 순서 정할 때 |
| [04_PROJECT_SPEC.md](./04_PROJECT_SPEC.md) | AI가 지켜야 할 규칙(절대 하지 마 / 항상 해) | AI에게 코드를 시킬 때마다 |

## 다음 단계

Phase 1을 시작하려면 [03_PHASES.md](./03_PHASES.md)의 "Phase 1 시작 프롬프트"를 참고하세요.

이 PRD는 godmode 파이프라인의 스테이지 B(골 세팅)로 이어집니다. goaljaby 미설치 상태이므로, 이 세션에서 직접 VALIDATION.md/LOOP.md를 작성해 골 루프를 대행합니다(직전 골과 동일한 폴백 방식 — 그 골의 기록은 `docs/superpowers/godmode-archive/2026-07-10-oneliner-tone-rewrite/`에 보관됨).

## 미결 사항

- "명사형 종결" 허용 어미 목록은 구현 단계에서 기존 문구의 실제 패턴을 추출해 확정.
- `_spicy_v2_positive_b.py` 파일 존재 여부는 구현 착수 시 확인.
