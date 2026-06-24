# Social Buzz Screener — 설계 문서

**날짜:** 2026-06-24  
**기능명:** 오늘의 WSB 픽 (소셜 버즈 스크리너 위젯)

---

## 개요

SwaggyStocks API를 활용해 WallStreetBets(Reddit)에서 언급량이 많고 긍정 감성을 보이는 종목을 발굴한다. 소셜 버즈로 후보를 좁힌 뒤 기존 TotalScore로 정렬해 메인 페이지 위젯에 표시한다.

---

## 목표

- WSB 언급량 多 + 긍정 감성인 종목을 자동으로 필터링
- 기존 TotalScore 기반 정렬로 "소셜 인기 + 퀀트 근거" 있는 종목 상위 5개 제공
- 메인 홈 화면에 즉시 노출되는 카드 위젯으로 제공

---

## 아키텍처

```
[SwaggyStocks API]
       ↓  (30분 주기 백그라운드 갱신)
[social_buzz.py — 캐시 + 필터]
       ↓  (티커 리스트)
[engine_adapter.ScanAdapter — TotalScore 조회]
       ↓  (정렬된 결과)
[GET /api/social-buzz]
       ↓  (JSON)
[메인 페이지 JS fetch → 카드 렌더링]
```

---

## 컴포넌트 설계

### 1. `web_app/social_buzz.py`

**역할:** SwaggyStocks API 호출, 캐시 관리, 필터링

**주요 로직:**
- 앱 시작 + 30분 주기로 백그라운드 스레드가 API 갱신
- 필터 조건: `mentions >= MENTIONS_MIN(기본 20)` AND `sentiment > 0`
- 필터 통과 종목 최대 20개를 `ScanAdapter`에 넘겨 TotalScore 조회
- 결과를 TotalScore 내림차순 정렬 후 상위 5개를 캐시에 저장
- API 실패 시 이전 캐시 유지 (silent fallback)

**캐시 구조:**
```python
_cache = {
    "items": [...],       # 최종 결과 리스트
    "updated_at": "ISO8601",
    "status": "ok" | "loading" | "error"
}
```

**SwaggyStocks API:**
- 대시보드: `https://swaggystocks.com/dashboard/wallstreetbets/ticker-sentiment`
- API 페이지: `https://swaggystocks.com/dashboard/wallstreetbets/ticker-sentiment/API`
- 공개 REST 문서 없음 — API 키 발급 후 실제 엔드포인트 확인 필요
- 제공 필드: Total Mentions, Bullish/Bearish/Neutral Counts, Net Sentiment
- 무료 플랜 rate limit 고려해 30분 간격 갱신
- **사전 조건:** `SWAGGY_API_KEY` 환경변수 설정 필요

---

### 2. `app.py` — API 엔드포인트 추가

```
GET /api/social-buzz
```

**응답 (정상):**
```json
{
  "status": "ok",
  "updated_at": "2026-06-24T11:30:00",
  "items": [
    {
      "ticker": "GME",
      "mentions": 312,
      "sentiment": 0.72,
      "total_score": 68,
      "grade": "B"
    }
  ]
}
```

**응답 (로딩 중):** `{"status": "loading"}`  
**응답 (에러):** `{"status": "error", "message": "..."}`

---

### 3. UI 위젯 — 메인 페이지

**위치:** 기존 홈 화면 상단 또는 적절한 섹션

**구성:**
- 섹션 헤더: "오늘의 WSB 픽 🔥" + 마지막 업데이트 시각
- 종목 카드 5개 (가로 스크롤):
  - 티커명 (강조)
  - 언급량 뱃지 (예: `312 mentions`)
  - 감성 바 (0~1 사이 진행 막대)
  - TotalScore 등급 (S/A/B/C)
- 카드 클릭 → 기존 종목 분석 드로어 오픈
- 로딩: 스켈레톤 카드
- 에러/빈 결과: "데이터 없음" 텍스트

**구현 방식:** 기존 `fetch` 패턴 재사용, 별도 JS 라이브러리 불필요

---

## 에러 처리

| 상황 | 처리 |
|------|------|
| API 호출 실패 | 이전 캐시 유지, status="error" 로그 |
| 캐시 미초기화 | status="loading" 반환 |
| 필터 통과 종목 0개 | 빈 items 배열 반환 |
| TotalScore 조회 실패 | 해당 종목 제외 후 나머지만 반환 |

---

## 환경 설정

`config_manager.py`를 통해 아래 값 오버라이드 가능:

- `SWAGGY_API_KEY` — SwaggyStocks API 키 **(필수)**
- `SOCIAL_BUZZ_REFRESH_MIN` — 캐시 갱신 주기 (기본: 30분)
- `SOCIAL_BUZZ_MENTIONS_MIN` — 최소 언급량 임계값 (기본: 20)
- `SOCIAL_BUZZ_TOP_N` — 위젯 표시 종목 수 (기본: 5)

---

## 기존 코드와의 관계

- `social_buzz.py`는 독립 모듈 — 기존 로직 변경 없음
- `engine_adapter.ScanAdapter` 재사용 — TotalScore 계산 중복 없음
- 백그라운드 스레드 패턴은 기존 `app.py`의 스캔 스케줄러와 동일 방식
- `yf_circuit.py`의 circuit breaker 패턴 참고해 API 장애 격리

---

## 범위 외 (이번 구현에서 제외)

- 소셜 데이터 DB 누적 저장 및 히스토리 트렌드
- 언급량 급등 알림
- WallStreetBets 외 다른 소셜 소스 (Twitter 등)
- 퀀트 점수 + 소셜 점수 가중 합산 복합 지표
