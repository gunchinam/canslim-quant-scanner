"""
etf.py — 인기 ETF 현황 수집 모듈 (미국 + 한국 동시)

별도 'ETF 현황' 탭에 표시할 대표 ETF들을 한 번에 모은다:
    각 ETF별 현재가, 전일 대비 등락률, 거래량(+평균 대비 배수), 52주 고저 위치

설계 원칙 (macro.py 와 동일):
  - yfinance 1회 배치 다운로드(period=1y) → 한 호출로 미·한 전부 수집
  - 종목별 독립 try/except → 일부 실패해도 나머지는 정상 표시
  - 인메모리 TTL 캐시 + stale-while-error (네트워크 실패 시 직전 값 유지)
  - 절대 예외를 밖으로 던지지 않는다 — 최악의 경우 빈 리스트 + stale 표기
  - /api/scan 과 완전히 분리 — 이 모듈의 어떤 예외도 스캔을 깨뜨리지 않는다
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone, timedelta

_LOG = logging.getLogger("etf")

_KST = timezone(timedelta(hours=9))

# 거래시간(KST 09~16시 한국 / 22~07시 미국, 평일)엔 15분, 그 외 60분
_TTL_TRADING_SEC = 15 * 60
_TTL_OFF_SEC = 60 * 60

# ── 캐시 ──────────────────────────────────────────────────────────────
_CACHE_LOCK = threading.Lock()
_CACHE: dict | None = None          # 마지막으로 성공 조립한 payload
_CACHE_TS: float = 0.0              # 캐시 적재 시각(epoch sec)

# ── 인기 ETF 목록 (티커, 한글 라벨) ───────────────────────────────────
# 리테일이 실제로 많이 거래하는 레버리지·테마(반도체·AI·빅테크) 중심 + 핵심 지수.
# ⚠ 3X/2X/인버스는 고위험 파생 상품 — 라벨에 배수 명시.
# 미국 — 레버리지(2X·3X)·인버스 중심 + 핵심
_US_ETFS: list[tuple[str, str]] = [
    ("SOXL", "반도체 3X"),         # Direxion 반도체 불 3배 — 서학개미 최애
    ("SOXS", "반도체 -3X"),        # 반도체 베어 3배(인버스)
    ("TQQQ", "나스닥 3X"),         # 나스닥100 3배
    ("SQQQ", "나스닥 -3X"),        # 나스닥100 -3배(인버스)
    ("SPXL", "S&P 3X"),           # S&P500 3배
    ("TNA",  "러셀2000 3X"),       # 미국 중소형 3배
    ("FNGU", "빅테크 3X"),         # FANG+ 3배
    ("MSTU", "마이크로스트래티지 2X"),  # MSTR 2배 — 2024~25 초인기
    ("NVDL", "엔비디아 2X"),
    ("TSLL", "테슬라 2X"),
    ("PLTU", "팔란티어 2X"),
    ("AMDL", "AMD 2X"),
    ("CONL", "코인베이스 2X"),
    ("BITX", "비트코인 2X"),
    ("ETHU", "이더리움 2X"),
    ("SMH",  "반도체"),            # 비레버리지 반도체 대표
    ("QQQ",  "나스닥 100"),
    ("SPY",  "S&P 500"),
    ("IBIT", "비트코인 현물"),
    ("ARKK", "혁신성장(ARK)"),
]

# 한국: KOSPI 상장 인기 ETF (.KS) — 레버리지/곱버스 + 반도체·AI 테마
_KR_ETFS: list[tuple[str, str]] = [
    ("122630.KS", "KODEX 레버리지"),              # 코스피 2배 — 거래대금 최상위
    ("252670.KS", "KODEX 인버스2X"),              # 코스피 -2배(곱버스)
    ("233740.KS", "KODEX 코스닥150 레버리지"),
    ("418660.KS", "TIGER 미국나스닥100 레버리지"),  # 서학개미 인기 레버리지
    ("409820.KS", "KODEX 미국나스닥100 레버리지"),
    ("465610.KS", "ACE 미국빅테크TOP7 레버리지"),
    ("267770.KS", "TIGER 200선물 레버리지"),
    ("396500.KS", "TIGER Fn반도체TOP10"),         # 국내 반도체 TOP10
    ("091160.KS", "KODEX 반도체"),
    ("390390.KS", "KODEX 미국반도체MV"),
    ("381180.KS", "TIGER 미국필라델피아반도체"),
    ("465580.KS", "ACE 미국빅테크TOP7"),
    ("305720.KS", "KODEX 2차전지산업"),
    ("466920.KS", "SOL 조선TOP3"),                # 2024~25 주도 테마
    ("133690.KS", "TIGER 미국나스닥100"),
    ("069500.KS", "KODEX 200"),                   # 핵심 지수
]


def _ttl_now() -> int:
    now = datetime.now(_KST)
    weekday = now.weekday() < 5
    kr_open = 9 <= now.hour < 16
    us_open = now.hour >= 22 or now.hour < 7
    trading = weekday and (kr_open or us_open)
    return _TTL_TRADING_SEC if trading else _TTL_OFF_SEC


def _row_from_sub(ticker: str, label: str, sub) -> dict | None:
    """yfinance 종목 서브프레임 → ETF 카드 1개 dict. 데이터 부족 시 None."""
    try:
        closes = sub["Close"].dropna()
        if len(closes) == 0:
            return None
        last = float(closes.iloc[-1])
        if last <= 0:
            return None
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
        change_pct = ((last - prev) / prev * 100.0) if prev else 0.0

        # 52주(가용 일봉 전체) 고·저 및 현재 위치(0~100%)
        hi52 = float(closes.max())
        lo52 = float(closes.min())
        span = hi52 - lo52
        pos52 = ((last - lo52) / span * 100.0) if span > 0 else 50.0
        pos52 = max(0.0, min(100.0, pos52))

        # 거래량 + 최근 20일 평균 대비 배수
        volume = None
        avg_vol = None
        vol_ratio = None
        try:
            vols = sub["Volume"].dropna()
            if len(vols):
                volume = int(vols.iloc[-1])
                tail = vols.tail(20)
                if len(tail):
                    avg_vol = int(tail.mean())
                    if avg_vol > 0:
                        vol_ratio = round(volume / avg_vol, 2)
        except Exception as ve:
            _LOG.debug("etf volume parse %s: %s", ticker, ve)

        return {
            "ticker": ticker,
            "label": label,
            "price": round(last, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "avg_vol": avg_vol,
            "vol_ratio": vol_ratio,
            "high52": round(hi52, 2),
            "low52": round(lo52, 2),
            "pos52": round(pos52, 1),
        }
    except Exception as e:
        _LOG.warning("etf: row parse %s failed: %s", ticker, e)
        return None


def _fetch() -> dict:
    """미·한 ETF 전부 1회 배치 호출 → {"us":[...], "kr":[...]}. 부분 실패 허용."""
    us_out: list[dict] = []
    kr_out: list[dict] = []

    all_pairs = [("US", t, l) for t, l in _US_ETFS] + [("KR", t, l) for t, l in _KR_ETFS]
    symbols = [t for _, t, _ in all_pairs]

    try:
        import yfinance as yf
        # auto_adjust=False → 배당 역조정 없는 실제 체결가(원가). 52주 고저를
        # 실제 거래 가격대로 표시하기 위함 (조정가의 소수점 KRW 회피).
        df = yf.download(
            symbols, period="1y", interval="1d",
            progress=False, group_by="ticker", threads=True,
            auto_adjust=False,
        )
    except Exception as e:
        _LOG.warning("etf: yfinance batch failed: %s", e)
        raise

    level0 = set(df.columns.get_level_values(0)) if hasattr(df.columns, "get_level_values") else set()
    for region, ticker, label in all_pairs:
        try:
            sub = df[ticker] if ticker in level0 else None
            if sub is None:
                continue
            row = _row_from_sub(ticker, label, sub)
            if row is None:
                continue
            (us_out if region == "US" else kr_out).append(row)
        except Exception as e:
            _LOG.warning("etf: %s parse failed: %s", ticker, e)

    return {"us": us_out, "kr": kr_out}


def _build() -> dict:
    data = _fetch()
    return {
        "us": data["us"],
        "kr": data["kr"],
        "ts": datetime.now(_KST).isoformat(timespec="seconds"),
        "stale": False,
    }


def get_etfs(force: bool = False) -> dict:
    """
    인기 ETF 현황 반환. TTL 캐시 + stale-while-error.

    절대 예외를 던지지 않는다 — 최악의 경우 빈 리스트 + stale 표기.
    """
    global _CACHE, _CACHE_TS
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE
        fresh = cached is not None and (now - _CACHE_TS) < _ttl_now()
        if fresh and not force:
            return cached

    try:
        payload = _build()
        # 양쪽 모두 비면 수집 실패로 간주 → stale 폴백 시도
        if not payload["us"] and not payload["kr"]:
            raise RuntimeError("empty result")
        with _CACHE_LOCK:
            _CACHE = payload
            _CACHE_TS = time.time()
        return payload
    except Exception as e:
        _LOG.warning("etf: build failed, serving stale: %s", e)
        with _CACHE_LOCK:
            if _CACHE is not None:
                stale = dict(_CACHE)
                stale["stale"] = True
                return stale
        return {
            "us": [], "kr": [],
            "ts": datetime.now(_KST).isoformat(timespec="seconds"),
            "stale": True,
        }


# ── 섹터 비중(sector weighting) — 카드 클릭 시 지연 로딩 ───────────────────
# 메인 /api/etf 배치를 느리게 만들지 않기 위해, 섹터 비중은 ETF 카드를
# 클릭한 순간에 per-ticker 로 따로 가져온다.
#   - 미국: yfinance funds_data.sector_weightings (영문 키 → 한글 라벨 매핑)
#   - 한국: 네이버 모바일증권 ETF 분석 API(sectorPortfolioList) 스크래핑
# 절대 예외를 밖으로 던지지 않는다 — 실패 시 빈 리스트(+stale) 반환.

_SECTOR_TTL_SEC = 6 * 60 * 60          # 섹터 구성은 거의 안 변함 → 6시간
_SECTOR_CACHE_MAX = 300                # 무제한 증가 차단(FIFO eviction)
_SECTOR_LOCK = threading.Lock()
_SECTOR_CACHE: dict[str, tuple[float, list]] = {}   # ticker -> (ts, sectors)

# yfinance funds_data.sector_weightings 영문 키 → 한글 라벨
_US_SECTOR_KR = {
    "technology":             "기술",
    "financial_services":     "금융",
    "healthcare":             "헬스케어",
    "consumer_cyclical":      "경기소비재",
    "consumer_defensive":     "필수소비재",
    "communication_services": "커뮤니케이션",
    "industrials":            "산업재",
    "energy":                 "에너지",
    "basic_materials":        "소재",
    "utilities":              "유틸리티",
    "realestate":             "부동산",
    "real_estate":            "부동산",
}

# 네이버 sectorPortfolioList detailTypeCode → 한글 라벨
_KR_SECTOR_KR = {
    "IT":                     "IT",
    "FINANCIALS":             "금융",
    "HEALTHCARE":             "헬스케어",
    "CONSUMER_DISCRETIONARY": "경기소비재",
    "CONSUMER_STAPLES":       "필수소비재",
    "COMMUNICATION":          "커뮤니케이션",
    "INDUSTRIALS":            "산업재",
    "ENERGY":                 "에너지",
    "MATERIALS":              "소재",
    "UTILITIES":              "유틸리티",
    "REAL_ESTATE":            "부동산",
    "UNCLASSIFIED":           "기타",
}


def _us_sectors(ticker: str) -> list[dict]:
    """yfinance funds_data.sector_weightings → [{label, weight_pct}] 내림차순."""
    import yfinance as yf
    fd = yf.Ticker(ticker).funds_data
    raw = fd.sector_weightings or {}
    out = []
    for key, w in raw.items():
        try:
            pct = float(w) * 100.0
        except (TypeError, ValueError):
            continue
        if pct <= 0:
            continue
        label = _US_SECTOR_KR.get(str(key).lower(), str(key))
        out.append({"label": label, "weight_pct": round(pct, 1)})
    out.sort(key=lambda r: r["weight_pct"], reverse=True)
    return out


def _kr_sectors(ticker: str) -> list[dict]:
    """네이버 ETF 분석 API sectorPortfolioList → [{label, weight_pct}] 내림차순."""
    code = ticker.split(".")[0]
    if not code.isdigit():
        return []
    url = "https://m.stock.naver.com/api/stock/%s/etfAnalysis" % code
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) scanner-etf",
            "Referer": "https://m.stock.naver.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    rows = data.get("sectorPortfolioList") or []
    out = []
    for r in rows:
        try:
            pct = float(r.get("weight"))
        except (TypeError, ValueError):
            continue
        if pct <= 0:
            continue
        code_ = str(r.get("detailTypeCode") or "")
        label = _KR_SECTOR_KR.get(code_, code_ or "기타")
        out.append({"label": label, "weight_pct": round(pct, 1)})
    out.sort(key=lambda r: r["weight_pct"], reverse=True)
    return out


def get_etf_sectors(ticker: str) -> dict:
    """
    ETF 한 종목의 섹터 비중 반환. per-ticker TTL 캐시.

    절대 예외를 던지지 않는다 — 실패 시 {"sectors": [], "stale": True}.
    반환: {"ticker", "sectors": [{label, weight_pct}], "stale": bool}
    """
    ticker = (ticker or "").strip()
    if not ticker:
        return {"ticker": ticker, "sectors": [], "stale": True}

    now = time.time()
    with _SECTOR_LOCK:
        hit = _SECTOR_CACHE.get(ticker)
        if hit is not None and (now - hit[0]) < _SECTOR_TTL_SEC:
            return {"ticker": ticker, "sectors": hit[1], "stale": False}

    is_kr = ticker.upper().endswith(".KS") or ticker.upper().endswith(".KQ")
    try:
        sectors = _kr_sectors(ticker) if is_kr else _us_sectors(ticker)
    except Exception as e:
        _LOG.warning("etf: sectors %s failed: %s", ticker, e)
        # stale-while-error: 직전 캐시가 있으면 그대로 반환
        with _SECTOR_LOCK:
            hit = _SECTOR_CACHE.get(ticker)
            if hit is not None:
                return {"ticker": ticker, "sectors": hit[1], "stale": True}
        return {"ticker": ticker, "sectors": [], "stale": True}

    with _SECTOR_LOCK:
        # FIFO eviction — 캐시 무한 증가 방지
        if len(_SECTOR_CACHE) >= _SECTOR_CACHE_MAX and ticker not in _SECTOR_CACHE:
            try:
                oldest = min(_SECTOR_CACHE, key=lambda k: _SECTOR_CACHE[k][0])
                _SECTOR_CACHE.pop(oldest, None)
            except ValueError:
                pass
        _SECTOR_CACHE[ticker] = (now, sectors)
    return {"ticker": ticker, "sectors": sectors, "stale": False}
