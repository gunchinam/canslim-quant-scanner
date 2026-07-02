# 점수 파이프라인 정합성 수정 + 표준화 재구축 + IC 검증 — 설계

날짜: 2026-07-02 (개정 v2 — 표준화 파이프라인 재구축 승인 반영)
목표: TotalScore가 **단기 스윙(수일~수주) 수익률 예측**이라는 목적에 맞게,
(A) 기존 파이프라인의 버그를 수정하고,
(B) 업계 표준(Barra/Grinold-Kahn 스타일 횡단면 표준화) 점수 파이프라인으로 재구축하며,
(C) 신/구 점수의 예측력을 forward IC로 비교 검증한다.

진행 순서: **Phase A(버그 수정) → Phase B(재구축) → Phase C(IC 검증)**.
Phase A를 유지하는 이유: 구 점수(`_LegacyScore`)가 Phase C의 비교 기준으로 남으므로, 비교가 공정하려면 구 파이프라인도 설계 의도대로 동작해야 한다.

---

## Phase A — 버그 수정 패키지 (기존 파이프라인)

### A-1. 드로다운 게이트 무효화 수정
- **현상**: STEP 10.6(`quant_nexus_v20.py:6125-6133`)이 `final`에 ×0.65(EXTREME)/×0.80(HIGH)을 곱하지만, STEP 10.7의 `final = composite_score`(`:6203`)가 이를 덮어쓴다. 5전략 루프(`:6161-6184`)는 저유동성 캡(`:6182`)만 적용하고 드로다운 감쇄는 미적용 → MDD 페널티가 최종 점수에 반영되지 않음.
- **수정**: 5전략 루프 내부에서 저유동성 캡과 같은 위치에 드로다운 승수를 적용한다 (`_f *= dd_mult`). 단일 경로(STEP 10.6)의 기존 적용은 유지 — `all_scores`가 비어 composite 덮어쓰기가 일어나지 않는 경로의 안전망. 태그 추가 로직은 현행 유지.
- **검증**: MDD EXTREME 종목의 TotalScore가 수정 전 대비 감소하는지 단위 테스트(모킹된 dd dict)로 확인.

### A-2. MoatBonus 멱등화 (이중 가산 차단)
- **현상**: `web_app/app.py:200-205`의 `_apply_moat_bonus`가 매 호출 `TotalScore += bonus`. 호출부 8곳(app.py:569, 814, 837, 909, 1014, 1527, 1854, 3600). 같은 row 리스트가 두 경로를 거치면(예: quick-warm 저장 → bg enrich 재저장) 보너스가 누적된다.
- **수정**: row에 `_MoatApplied` 플래그를 세우고, 플래그가 있으면 스킵. `force` 재계산 경로(`_annotate_moats(force=True)`)에서는 플래그 제거 후 재적용.
- **검증**: 같은 리스트에 `_apply_moat_bonus` 2회 호출 시 TotalScore가 1회 호출과 동일한지 단위 테스트.

### A-3. midcap_alpha의 moat 이중 반영 제거
- **현상**: `web_app/engine_adapter.py:292,304` — `ts`(이미 MoatBonus 반영 가능)를 쓰면서 promo에 `min(15, moat*5)`를 또 가산.
- **수정**: promo 식에서 `min(15, moat*5)` 항 제거. moat 기여는 ts(alpha의 0.3 가중)를 통해 1회만 반영.
- **검증**: moat=2인 SP400 종목의 promo가 수정 전 대비 10점 감소 확인.

### A-4. 죽은 설정 상수 정리
- **현상**: `SUPER_MULT_MIN=1.20`/`SUPER_MULT_MAX=1.50`(`quant_nexus_v20.py:686-687`)은 미사용. 실제 슈퍼그로스 승수는 인라인 1.05~1.18(`:6088-6104`).
- **수정**: 두 상수를 삭제하고, 인라인 승수 4단계(1.18/1.14/1.10/1.07, 부분충족 1.05)를 CANSLIM 설정 dict의 명명 상수로 끌어올려 STEP 9와 5전략 루프가 같은 값을 참조하게 한다.
- **검증**: 수정 전후 동일 입력의 TotalScore 불변(리팩터링만) 확인.

### A-5. 스테일 캐시 점수 감쇄 페널티
- **현상**: yfinance 실패 시 최대 7일 전 캐시 점수가 `DataStatus=STALE_CACHE` 플래그만 달고(`quant_nexus_v20.py:5363-5377`) 신선한 점수와 동일하게 랭킹 경쟁. 백엔드에서 이 플래그를 쓰는 곳이 없음.
- **수정**: stale 폴백 시점에 `TotalScore -= min(15, 3 × days_back)` 감쇄를 적용하고(`_RawTotalScore`에 원본 보존, 바닥 0), `StaleDays` 필드를 추가한다. 당일 키(days_back=0)는 무감쇄.
- **검증**: days_back=3 stale row의 TotalScore가 9점 감소 + StaleDays=3 확인.

### Phase A 공통
- 각 수정은 개별 커밋. 기존 동작 회귀는 `tests/` + 격리 단위 테스트로 확인.
- (구버전 A-6 "레이어별 승수 기록"은 삭제 — Phase B의 `_Factors` 기록이 대체한다.)

---

## Phase B — 횡단면 표준화 점수 파이프라인 재구축 (ScoreV2)

### 방법론적 근거
- **횡단면 z-score 표준화 + 가중합 + 순위화**: Barra/MSCI 팩터 모델, Grinold & Kahn *Active Portfolio Management*의 표준 절차. 팩터를 winsorize → 유니버스 횡단면 z-score → 가중합 → 백분위 순위로 변환한다.
- **곱셈 승수 스택 제거의 근거**: VIX·매크로레짐·Bear Cap은 **전 종목에 동일하게 곱해지는 시장 전역 승수**라 횡단면 순위를 전혀 바꾸지 못한다(점수 압축만 발생). 순위 기반 점수에서는 무의미하므로 점수에서 제거하고 시장 컨텍스트 표시로 이동한다.
- **단기 스윙 팩터 보강**: 단기 반전(Jegadeesh 1990, Lehmann 1990 — 1주 수익률 역방향), 52주 신고가 근접도(George & Hwang 2004), 중기 모멘텀 12-1(Jegadeesh & Titman 1993). 원시 값(`dist_from_52w_high`, 평균회귀 팩터 등)은 이미 계산되고 있어 결합만 추가하면 된다.

### 아키텍처
현재 구조는 종목별 독립 계산(`_analyze_ticker`, 병렬+캐시)이라 횡단면 처리를 할 수 없다. 따라서 2단 구조로 분리한다:

1. **팩터 산출 (종목별, 기존 코드 재사용)**: `_analyze_ticker`가 STEP 1~3에서 이미 계산하는 정규화 팩터 23개(f_momentum … f_bb_revert)와 단기 반전용 원시값(5일 수익률), `dist_from_52w_high`를 row의 `_Factors` dict(경량 스칼라)로 저장한다. 캐시에도 함께 저장되므로 캐시 히트 시에도 사용 가능.
2. **횡단면 결합 (유니버스 단위, 신규 모듈 `web_app/score_v2.py`)**: `scan_all`/`scan_sector` 집계 직후 전체 rows에 대해:
   - **winsorize**: 팩터별 MAD 기반 ±3σ 클립 (극단값 왜곡 차단)
   - **z-score**: 팩터별 횡단면 표준화 (표본<10이면 스킵하고 legacy 점수 유지 — 소표본 왜곡 방지)
   - **가중합**: 문서화된 초기 가중치(아래) — Phase C의 IC 결과로 추후 재조정
   - **백분위 순위 → 0~100**: 유니버스 내 순위 백분위가 TotalScore가 된다

### 초기 가중치 (단기 스윙 지향, Phase C에서 IC로 재검증)
| 팩터군 | 가중 | 구성 |
|---|---|---|
| 중기 모멘텀 | 0.25 | f_momentum, f_rs (12-1 모멘텀·상대강도) |
| 단기 반전 | 0.15 | 5일 수익률 역방향 (과열 진입 회피) |
| 52주 신고가 근접 | 0.15 | 1 − dist_from_52w_high |
| 수급/스마트머니 | 0.15 | f_volume, f_smart_money |
| 품질/펀더멘털 | 0.15 | f_quality, f_fama_french |
| 기술적 셋업 | 0.15 | f_mtf, f_bb_revert, f_orb, f_nr7 |

### 게이트 → 플래그 분리
점수를 변조하던 캡·승수를 `RiskFlags: list[str]` 필드로 분리한다:
- `EPS_NEGATIVE`(적자), `LOW_LIQUIDITY`(거래대금 부족), `MDD_EXTREME`/`MDD_HIGH`, `BEAR_MARKET`
- 점수는 순수 순위를 유지하고, **시그널 라벨(STRONG BUY 등) 결정 시에만** 플래그로 강등한다(예: LOW_LIQUIDITY → BUY 상한, MDD_EXTREME → HOLD 상한). 시그널 임계는 기존 값(90/82/72/60/48/35) 유지.
- VIX·매크로레짐은 종목 점수에서 제거하고 시장 단위 `MarketContext` 필드(스캔 응답 메타)로 이동.

### 제거 대상 (v2 경로에서)
- 슈퍼그로스 승수(임의 1.05~1.18), Hurst/Kalman trust(±4~6%), 5전략 composite·disagreement penalty, VIX/매크로 승수, Bear Cap, 드로다운 곱셈 감쇄(→ 플래그화).
- **legacy 경로는 그대로 남긴다**: 기존 12단계 산출을 `_LegacyScore` 필드로 병행 기록 — Phase C 비교 기준 + 롤백 대비.

### 전환·롤백
- `TotalScore` = v2 백분위 점수. UI/정렬/사후보정(moat, 투기주 캡, regime weighting)은 TotalScore를 그대로 소비하므로 **하류 변경 불요**.
- MoatBonus 가산(0~10)·투기주 캡(59)은 리스크 컨트롤 목적의 별도 레이어로 유지(v2 점수 위에 기존처럼 적용).
- env `SCORE_V2=0`이면 TotalScore에 legacy 값을 사용(원클릭 롤백).
- 점수 의미가 "절대 품질"→"유니버스 내 백분위"로 바뀌므로 분포가 균등화된다. 시그널 임계와의 정합은 v2 배포 직후 분포 확인으로 점검.

### 검증
- 단위 테스트: winsorize/z-score/백분위 함수(고정 입력→고정 출력), 소표본 스킵, RiskFlags 강등 규칙.
- 통합: 실제 스냅샷 1개로 v2 점수 산출 → 상위 20 종목을 legacy 상위 20과 비교하는 리포트 생성(수동 눈검증).

---

## Phase C — forward IC 검증 하니스

### 목적
(1) **v2 vs legacy 예측력 직접 비교**, (2) v2 팩터별 IC 측정으로 가중치 재조정 근거 확보.

### 설계
- 새 모듈 `score_ablation.py`(루트): `history` 스냅샷에 기록된 `_Factors`·`_LegacyScore`·TotalScore를 point-in-time으로 읽어 forward 5/10/20 거래일 수익률과의 Spearman IC를 계산.
- 비교 축: v2 TotalScore vs `_LegacyScore` vs 개별 팩터군 6종 vs 등가중 결합.
- 통계: `regime_ic.py`의 Newey-West HAC·블록 부트스트랩 유틸 재사용. 표본 부족 시 INSUFFICIENT 명시.
- 출력: `cache_v19/score_ablation_report.json` + 콘솔 표. 실행은 수동 CLI(`python score_ablation.py --horizon 10`).
- 판독 기준: 4주+ 누적 후, v2 IC ≥ legacy IC이면 legacy 경로 제거 검토, 팩터군 IC로 가중치 재조정(Grinold-Kahn IC 비례 가중은 그 시점의 별도 결정).

### 한계
- `_Factors` 기록은 Phase B 배포 시점부터 누적 — 소급 불가. 최소 4주 누적 후 1차 판독.

---

## 스코프 밖
- IC 기반 동적 가중치 자동 재조정(데이터 누적 후 별도 설계).
- 프론트엔드 STALE/RiskFlags 표시 개선(별도 UI 작업).
- 섹터 중립화(sector-neutral z-score) — 1차 배포는 전체 유니버스 기준, 필요성은 Phase C 결과로 판단.
