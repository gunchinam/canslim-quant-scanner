# TradingKey + 노무라式 통합 설계 문서

**작성일:** 2026-06-25  
**프로젝트:** 종목스캐너  
**상태:** UX 확정 → 구현 대기

---

## 1. 개요

TradingKey의 내부 JSON API에서 미국 종목 데이터를 수집하고, 노무라 증권의 리서치 방법론을 참고한 **노무라式** 정량 스코어링 시스템을 구축한다. 기존 드로어·차트·스크리너에 통합하여 기관급 분석 경험을 제공한다.

> ⚠️ "노무라式"는 노무라 증권의 공식 서비스가 아닌 방법론에서 영감을 받은 독립 구현이다.

---

## 2. 데이터 레이어

### 2-1. `tradingkey_api.py` (신규)

**역할:** TradingKey 내부 API를 curl_cffi로 호출, 파싱, 캐싱  
**적용 대상:** 미국 종목 전용 (KR 종목 — 6자리 숫자, `.KS`/`.KQ` 접미사 — 자동 스킵)

```python
# 공개 인터페이스
def get_tradingkey_data(ticker: str) -> dict | None
def get_score(ticker: str) -> dict | None
def get_support_resistance(ticker: str) -> tuple[float, float] | None

# 캐시 패턴 (finnhub_api.py와 동일)
_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 4 * 3600  # 4시간

# curl_cffi — Chrome TLS 핑거프린트 위장
from curl_cffi import requests as cffi_requests
session = cffi_requests.Session(impersonate="chrome120")
```

**데이터 스키마 (7-레이어):**

```python
TradingKeyData = {
    "score": {
        "overall": int,           # 0~100 종합점수
        "valuation": int,
        "growth": int,
        "profitability": int,
        "momentum": int,
        "risk": int,
        "industry_rank": int,
        "industry_total": int,
        "overall_rank": int,
        "overall_total": int,
        "sector_percentile": float,
    },
    "institutional": {
        "confidence_score": float,
        "holding_pct": float,
        "holding_qoq": float,     # QoQ 변화 (핵심 지표)
        "top_holder": str,
        "top_holder_pct": float,
        "top_holder_chg": float,
    },
    "analyst": {
        "consensus": str,         # "Buy" / "Hold" / "Sell"
        "target_price": float,
        "upside_pct": float,
        "analyst_count": int,
        "buy_count": int,
        "hold_count": int,
        "sell_count": int,
    },
    "valuation": {
        "pe_ttm": float,
        "pe_dynamic": float,
        "pe_static": float,
        "pb": float,
        "eps_ttm": float,
        "market_cap": float,
    },
    "fundamentals": {
        "roe": float,
        "roa": float,
        "gross_margin": float,
        "net_profit": float,
        "dividend_yield": float,
        "payout_ratio": float,
    },
    "risk_technical": {
        "beta": float,
        "risk_rate": float,
        "reward_risk": float,
        "support": float,         # 지지선
        "resistance": float,      # 저항선
        "volume_ratio": float,
        "amplitude": float,
        "turnover_ratio": float,
    },
    "performance": {
        "1d": float, "5d": float, "1m": float,
        "6m": float, "ytd": float, "1y": float,
    },
    "_cached_at": float,
    "_source": "tradingkey",
}
```

**API 엔드포인트 발굴 방법:**  
브라우저 DevTools → Network 탭 → TradingKey 종목 페이지 로드 → XHR/Fetch 요청에서 JSON 응답 확인 → `curl_cffi`로 재현

---

### 2-2. `nomura_score.py` (신규)

**역할:** TradingKey + yfinance 데이터로 노무라式 정량 스코어 산출

**반환 스키마:**

```python
{
    "quantitative_score": int,   # 0~100
    "grade": str,                # "A+" / "A" / "B" / "C" / "D"
    "piotroski": int,            # 0~9 (F-Score)
    "altman_z": float,           # >2.99: 안전, 1.81~2.99: 회색, <1.81: 위험
    "beneish_m": float,          # <-1.78: 정상, >-1.78: ⚠️ 분식 의심
    "beneish_warning": bool,
    "nomura_rating": str,        # "Conviction Buy" / "Buy" / "Neutral" / "Reduce"
    "nomura_target": float,      # 목표주가
    "nomura_upside": float,      # 현재가 대비 업사이드 %
}
```

**100점 배점 구조:**

| 카테고리 | 배점 | 세부 지표 |
|----------|------|-----------|
| QoQ 모멘텀 | 20점 | 기관지분 QoQ, 매출 QoQ, EPS QoQ |
| YoY 성장성 | 20점 | 매출 YoY, 순이익 YoY, ROE 추세 |
| 밸류에이션 | 30점 | PER 섹터 비교, PBR, EV/EBITDA |
| 수익성 | 30점 | Gross Margin, ROA, Piotroski F-Score |

**레이팅 기준:**

| 점수 | 등급 | 노무라式 레이팅 |
|------|------|-----------------|
| 90~100 | A+ | Conviction Buy |
| 75~89 | A | Buy |
| 55~74 | B | Neutral |
| 35~54 | C | Reduce |
| 0~34 | D | Sell |

---

## 3. 드로어 UI 통합

### 선택: B — 아코디언 인라인형

기존 드로어 섹션 아래 접기/펼치기 아코디언으로 6개 신규 섹션 추가.  
기본 상태: TK Score 섹션만 펼침, 나머지 접힘.

**신규 섹션 목록:**

| 섹션 | 기본 | 데이터 소스 |
|------|------|-------------|
| 📊 TK Score | 펼침 | tradingkey_api |
| 🏦 노무라式 스코어 & 레이팅 | 접힘 | nomura_score |
| 🏛 기관 투자자 현황 | 접힘 | tradingkey_api |
| ⚽ Football Field 밸류에이션 | 접힘 | tradingkey_api + nomura_score |
| 📅 Catalyst Roadmap | 접힘 | event_calendar (확장) |
| 🔍 예측 Audit | 접힘 | history (확장) |

---

## 4. Football Field 시각화

### 선택: B — 히트맵 분위수형

각 밸류에이션 방법론별로 저평가↔고평가 스펙트럼을 색상 그라데이션으로 표현.  
현재가 위치를 `▼` 마커로 표시, 우측에 저평가/적정/고평가 텍스트 출력.

**구현 위치:** 드로어 내 Football Field 섹션 (HTML Canvas 또는 CSS div)

**밸류에이션 방법론 4개:**
1. PER 섹터 비교
2. TK 애널리스트 목표가
3. TK 지지선/저항선
4. Fibonacci 0.618 레벨

---

## 5. 핸드드로잉 차트 강화

### 선택: A — 풀레이어 표시형

`handdrawn_renderer.py`에 matplotlib 레이어 추가. 기존 레이어(EMA·BB·GreedZone) 위에 순서대로 렌더링.

**신규 레이어 (⑤~⑨):**

| 레이어 | 구현 | 색상 |
|--------|------|------|
| ⑤ Fibonacci 수평선 | `axhline(dashes=...)` | 보라 (#a78bfa) |
| ⑥ S/R 수평점선 | `axhline(linestyle='--')` | 빨강/초록 |
| ⑦ Catalyst 수직선 | `axvline(dashes=...)` | 주황 (#f59e0b) |
| ⑧ Football Field 우측 레이블 | `ax.text(transform=blended)` | 회색 |
| ⑨ 노무라式 배지 | `ax.text` + FancyBboxPatch | 파랑 테두리 |

**레이어 제어 파라미터:**
```python
generate_chart(
    ticker, period,
    show_fib=True,
    show_sr=True,
    show_catalyst=True,
    show_nomura_badge=True,
)
```

**Fibonacci 자동 계산:**
- 조회 기간 내 최고가(H), 최저가(L) 탐지
- 레벨: `L + (H-L) * ratio` for ratio in [0.236, 0.382, 0.5, 0.618, 0.786]
- Extension: `H + (H-L) * 0.272`, `H + (H-L) * 0.618`

---

## 6. 노무라式 레이팅 배지

### 선택: C — 게이지 원형 배지

**차트 내 배치:** 우상단 (matplotlib `ax.inset_axes` 또는 FancyBboxPatch)  
**드로어 내 배치:** 노무라式 섹션 상단 KPI 카드

**배지 구성 요소:**
- 원형 게이지: 스코어 0~100을 호(arc) 길이로 표현
- 중앙 텍스트: 레이팅 (BUY / C.BUY / NEUTRAL / REDUCE)
- 하단: 목표주가 + 업사이드 %
- 색상 코드: C.BUY=파랑, BUY=초록, NEUTRAL=노랑, REDUCE=빨강

---

## 7. 스크리너 위젯

### 선택: C — 필터칩 + 스파크라인형

**위치:** 메인 스크리너 새 탭 "TK 스코어"

**필터 칩 (기본 ON):**
- `TK ≥ 70`
- `기관 QoQ ↑`  
- `업사이드 ≥ 5%`
- `BUY만` (선택)

**각 종목 행 구성:**
- 순위 번호
- 티커 + 레이팅 뱃지
- 부제 (기관 QoQ · 업사이드 %)
- 미니 스파크라인 (50일 SVG polyline)
- TK 스코어 숫자

**구현 파일:** `web_app/static/app.js` + `web_app/templates/scanner.html`

---

## 8. AI 분석 강화

### 8-1. 투자위원회 Phase 7 (`persona_committee.py` 확장)

5인 가상 위원이 노무라式 데이터를 입력받아 독립 의견 제시:

| 위원 | 관점 | 주요 입력 데이터 |
|------|------|-----------------|
| 펀더멘털 애널리스트 | 재무·밸류에이션 | Piotroski, Altman Z, PER |
| 모멘텀 트레이더 | 기술적·모멘텀 | TK risk_technical, performance |
| 매크로 전략가 | 거시경제·섹터 | 섹터 백분위, Beta |
| 리스크 매니저 | 리스크·시나리오 | Beneish M, Altman Z, Beta |
| 포트폴리오 매니저 | 종합 판단 | 전원 의견 취합 |

출력: 각 위원 의견 + 확신도(%) + 최종 노무라式 레이팅

### 8-2. Catalyst Roadmap (`event_calendar.py` 확장)

기존 이벤트 스키마에 3개 필드 추가:
```python
{
    "date": str,
    "event": str,
    "impact_direction": str,   # "positive" / "negative" / "neutral"
    "strength": str,           # "high" / "medium" / "low"
    "probability": float,      # 0.0 ~ 1.0
}
```

### 8-3. 예측 Audit Phase 0 (`history.py` 확장)

과거 노무라式 레이팅 스냅샷 저장 → 실제 주가와 자동 대조:
```python
{
    "ticker": str,
    "rating": str,
    "target_price": float,
    "rated_at": str,       # ISO timestamp
    "rated_price": float,  # 레이팅 당시 주가
    "verified_at": str,    # 검증 시점
    "actual_price": float,
    "hit": bool,           # 목표가 달성 여부
}
```

---

## 9. 구현 순서 (권장)

```
Phase 1: tradingkey_api.py 구현 (API 역공학 + 캐시)
Phase 2: nomura_score.py 구현 (스코어링 엔진)
Phase 3: 드로어 TK Score 섹션 (아코디언 B)
Phase 4: 드로어 노무라式 + Football Field (히트맵 B)
Phase 5: handdrawn_renderer.py 레이어 추가 (풀레이어 A)
Phase 6: 노무라式 배지 (원형 게이지 C)
Phase 7: 스크리너 위젯 (필터칩+스파크라인 C)
Phase 8: persona_committee.py 투자위원회 확장
Phase 9: event_calendar.py Catalyst Roadmap
Phase 10: history.py 예측 Audit
```

---

## 10. 기술 의존성

| 라이브러리 | 용도 | 상태 |
|-----------|------|------|
| `curl_cffi` | TradingKey API 호출 | 설치됨 (.venv64) |
| `yfinance` | 재무 데이터 (Piotroski 등) | 기존 사용 중 |
| `matplotlib` | 차트 레이어 추가 | 기존 사용 중 |
| `numpy` | Fibonacci 계산 | 기존 사용 중 |

---

## 11. 범위 외 (이번 구현 제외)

- 한국 종목 TradingKey 연동 (커버리지 부족)
- 실시간 WebSocket 스트리밍
- 노무라式 백테스팅 엔진
- 투자위원회 음성 출력
