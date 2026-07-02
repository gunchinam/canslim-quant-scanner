# 점수 파이프라인 정합성 수정 + IC 검증 하니스 — 설계

날짜: 2026-07-02
목표: TotalScore가 **단기 스윙(수일~수주) 수익률 예측**이라는 목적에 맞게, (A) 설계 의도대로 계산되도록 버그를 수정하고, (B) 각 보정 레이어의 예측 기여를 데이터로 검증하는 하니스를 구축한다.

진행 순서: **Phase A(버그 수정) → Phase B(IC 검증 하니스)**. Phase B의 결과에 따라 레이어 제거/재조정(추후 Phase C)을 결정한다.

---

## Phase A — 버그 수정 패키지

### A-1. 드로다운 게이트 무효화 수정
- **현상**: STEP 10.6(`quant_nexus_v20.py:6125-6133`)이 `final`에 ×0.65(EXTREME)/×0.80(HIGH)을 곱하지만, STEP 10.7의 `final = composite_score`(`:6203`)가 이를 덮어쓴다. 5전략 루프(`:6161-6184`)는 저유동성 캡(`:6182`)만 적용하고 드로다운 감쇄는 미적용 → MDD 페널티가 최종 점수에 반영되지 않음.
- **수정**: 5전략 루프 내부에서 저유동성 캡과 같은 위치에 드로다운 승수를 적용한다 (`_f *= dd_mult`). 단일 경로(STEP 10.6)의 기존 적용은 유지 — `all_scores`가 비어 composite 덮어쓰기가 일어나지 않는 경로의 안전망. 태그 추가 로직은 현행 유지(이미 STEP 10.6에서 1회만 추가).
- **검증**: MDD EXTREME 종목의 TotalScore가 수정 전 대비 감소하는지 단위 테스트(모킹된 dd dict)로 확인.

### A-2. MoatBonus 멱등화 (이중 가산 차단)
- **현상**: `web_app/app.py:200-205`의 `_apply_moat_bonus`가 매 호출 `TotalScore += bonus`. 호출부 8곳(app.py:569, 814, 837, 909, 1014, 1527, 1854, 3600). 같은 row 리스트가 두 경로를 거치면(예: quick-warm 저장 → bg enrich 재저장) 보너스가 누적된다.
- **수정**: row에 `_MoatApplied` 플래그를 세우고, 플래그가 있으면 스킵. `force` 재계산 경로(`_annotate_moats(force=True)`)에서는 플래그 제거 후 재적용.
- **검증**: 같은 리스트에 `_apply_moat_bonus` 2회 호출 시 TotalScore가 1회 호출과 동일한지 단위 테스트.

### A-3. midcap_alpha의 moat 이중 반영 제거
- **현상**: `web_app/engine_adapter.py:292,304` — `ts`(이미 MoatBonus 반영 가능)를 쓰면서 promo에 `min(15, moat*5)`를 또 가산. MidcapAlpha는 별도 필드지만 해자 종목이 이중 우대된다.
- **수정**: promo 식에서 `min(15, moat*5)` 항 제거. moat 기여는 ts(alpha의 0.3 가중)를 통해 1회만 반영.
- **검증**: moat=2인 SP400 종목의 promo가 수정 전 대비 10점 감소 확인.

### A-4. 죽은 설정 상수 정리
- **현상**: `SUPER_MULT_MIN=1.20`/`SUPER_MULT_MAX=1.50`(`quant_nexus_v20.py:686-687`)은 미사용. 실제 슈퍼그로스 승수는 인라인 1.05~1.18(`:6088-6104`).
- **수정**: 두 상수를 삭제하고, 인라인 승수 4단계(1.18/1.14/1.10/1.07, 부분충족 1.05)를 CANSLIM 설정 dict의 명명 상수로 끌어올려 STEP 9와 5전략 루프가 같은 값을 참조하게 한다.
- **검증**: 수정 전후 동일 입력의 TotalScore 불변(리팩터링만) 확인.

### A-5. 스테일 캐시 점수 감쇄 페널티
- **현상**: yfinance 실패 시 최대 7일 전 캐시 점수가 `DataStatus=STALE_CACHE` 플래그만 달고(`quant_nexus_v20.py:5363-5377`) 신선한 점수와 동일하게 랭킹 경쟁. 백엔드에서 이 플래그를 쓰는 곳이 없음.
- **수정**: stale 폴백 시점에 `_days_back`을 알고 있으므로, `TotalScore -= min(15, 3 × days_back)` 감쇄를 적용하고(`_RawTotalScore`에 원본 보존, 바닥 0), `StaleDays` 필드를 추가한다. 하루 이내(당일 키, days_back=0)는 무감쇄.
- **근거**: 단기 스윙 목적에서 점수의 정보 가치는 일 단위로 소멸. 완전 제외 대신 감쇄로 처리해 유니버스 급감(rate-limit 대량 발생 시)을 피한다.
- **검증**: days_back=3 stale row의 TotalScore가 9점 감소 + StaleDays=3 확인.

### A-6. 레이어별 승수 기록 (Phase B 선행 작업)
- **내용**: STEP 5~10.7에서 적용되는 승수·페널티를 row에 경량 스칼라로 기록한다: `_VixMult`, `_MacroMult`, `_SuperMult`, `_DDMult`, `_VolAdjDelta`, `_DisagreementPenalty`. `_strip_heavy`의 제거 대상에서 제외해 스냅샷에 보존.
- **근거**: Phase B의 레이어 ablation이 point-in-time 재구성을 하려면 당시 적용된 승수를 알아야 한다. 지금 기록을 시작해야 4주 뒤 판독이 가능.
- **검증**: 스캔 결과 row에 6개 필드가 존재하고, `final ≈ base × 승수들` 관계가 재구성되는지 단위 테스트.

### Phase A 공통
- 각 수정은 개별 커밋. 기존 동작 회귀는 `tests/` + 격리 단위 테스트로 확인.
- 점수 분포가 바뀌므로(특히 A-1, A-5) 배포 후 스캔 캐시는 자연 만료로 갱신됨 — 별도 마이그레이션 불요.

## Phase B — IC 귀속 검증 하니스

### 목적
"이 보정 레이어가 단기 수익률 예측(IC)에 실제 기여하는가"를 레이어별 ablation으로 측정. 현재 `web_app/score_eval.py`는 최종 표시 점수의 IC만 측정해 개별 가중치·승수에 귀속 불가.

### 설계
- **새 모듈 `score_ablation.py`** (루트): 스냅샷(`history` 모듈이 저장하는 일별 스캔 결과)에서 point-in-time 점수 구성요소를 읽어, 레이어 on/off 변형 점수를 재구성한다.
  - 재구성에 필요한 레이어별 승수 기록은 A-6에서 선행 구축된다.
  - 변형: `no_vix`, `no_macro`, `no_super`, `no_dd`, `no_voladj`, `no_composite`(단일 경로 점수), `raw_base`(STEP 4 가중합만).
- **평가**: 각 변형 점수 vs forward 5/10/20 거래일 수익률의 Spearman IC. `regime_ic.py`의 Newey-West/블록 부트스트랩 유틸 재사용. 표본 부족 시 INSUFFICIENT 명시.
- **출력**: `cache_v19/score_ablation_report.json` + 콘솔 표. 판단 기준: 레이어 제거 시 IC가 유의하게 오르면 해당 레이어는 제거/재조정 후보.
- **실행**: 수동 CLI(`python score_ablation.py --horizon 10`). 자동 피드백 루프는 스코프 밖(Phase C 후보).

### 한계
- 스냅샷 누적 기간만큼만 평가 가능(소급 불가 레이어 존재). 최소 4주 누적 후 1차 판독을 권장.

## 스코프 밖
- 가중치 w[] 자체의 재튜닝, 점수 아키텍처 재구성(품질/타이밍 분리) — Phase B 결과 확보 후 별도 설계.
- 프론트엔드 STALE 표시 개선.
