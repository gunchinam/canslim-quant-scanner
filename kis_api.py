# -*- coding: utf-8 -*-
"""kis_api.py — 한국투자증권 Open API 클라이언트 (실시간 현재가 + 스크리너용 데이터).

.env 변수 (D:\\Download\\scalping_final\\.env 자동 로드):
    IS_MOCK=false           → 실전투자 (KIS_REAL_APP_KEY / KIS_REAL_APP_SECRET 사용)
    IS_MOCK=true            → 모의투자 (APP_KEY / APP_SECRET 사용)
    KIS_REAL_APP_KEY        — 실전 앱 키
    KIS_REAL_APP_SECRET     — 실전 앱 시크릿
    APP_KEY                 — 모의 앱 키
    APP_SECRET              — 모의 앱 시크릿
    KIS_REAL_ACCOUNT_NO     — 실전 계좌번호
    ACCOUNT_NO              — 모의 계좌번호

공개 API:
    get_price(code)                              → dict  (현재가·전일대비율)
    get_prices(codes)                            → dict[code, dict]  (병렬 조회)
    get_volume_rank(top_n=100)                   → list[dict]  (거래대금 상위 종목)
    get_investor_trend(code)                     → dict  (외인/기관/프로그램 순매수)
    get_minute_candles(code, period=30, count=20) → list[dict]  (분봉 데이터)
    is_available()                               → bool
"""
from __future__ import annotations

import os
import json
import time
import datetime as _dt
import threading
import urllib.request
from typing import Any, Dict, List, Optional

# .env 자동 로드
try:
    import _env_loader  # noqa: F401
except Exception:
    pass

# ── 엔드포인트 ────────────────────────────────────────────────────────────────
_REAL_BASE = "https://openapi.koreainvestment.com:9443"
_MOCK_BASE = "https://openapivts.koreainvestment.com:29443"


def _is_mock() -> bool:
    return os.environ.get("IS_MOCK", "false").strip().lower() in ("true", "1", "yes")


def _base() -> str:
    return _MOCK_BASE if _is_mock() else _REAL_BASE


# ── 인증 정보 ─────────────────────────────────────────────────────────────────
def _app_key() -> str:
    if _is_mock():
        return (os.environ.get("APP_KEY") or
                os.environ.get("KIS_MOCK_APP_KEY") or
                os.environ.get("KIS_APP_KEY", "")).strip()
    return (os.environ.get("KIS_REAL_APP_KEY") or
            os.environ.get("KIS_APP_KEY", "")).strip()


def _app_secret() -> str:
    if _is_mock():
        return (os.environ.get("APP_SECRET") or
                os.environ.get("KIS_MOCK_APP_SECRET") or
                os.environ.get("KIS_APP_SECRET", "")).strip()
    return (os.environ.get("KIS_REAL_APP_SECRET") or
            os.environ.get("KIS_APP_SECRET", "")).strip()


def _account_no() -> str:
    if _is_mock():
        return (os.environ.get("ACCOUNT_NO") or
                os.environ.get("KIS_MOCK_ACCOUNT_NO", "")).strip()
    return (os.environ.get("KIS_REAL_ACCOUNT_NO") or
            os.environ.get("ACCOUNT_NO", "")).strip()


def is_available() -> bool:
    """APP_KEY / APP_SECRET 가 설정됐으면 True."""
    return bool(_app_key() and _app_secret())


# ── 토큰 관리 (스레드 안전, 파일 캐시로 프로세스 간 재사용) ─────────────────
_token_lock: threading.Lock = threading.Lock()
_token_value: Optional[str] = None
_token_expire: float = 0.0
_TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".kis_token_cache.json")


def _load_token_cache() -> tuple[Optional[str], float]:
    """파일 캐시에서 토큰 로드."""
    try:
        with open(_TOKEN_CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        token  = d.get("token")
        expire = float(d.get("expire", 0))
        key    = d.get("key", "")
        # 키가 바뀌었으면 무효화
        if key != _app_key():
            return None, 0.0
        return token, expire
    except Exception:
        return None, 0.0


def _save_token_cache(token: str, expire: float) -> None:
    """토큰을 파일 캐시에 저장."""
    try:
        with open(_TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"token": token, "expire": expire, "key": _app_key()}, f)
    except Exception:
        pass


def _fetch_token() -> tuple[str, float]:
    url  = f"{_base()}/oauth2/tokenP"
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey":     _app_key(),
        "appsecret":  _app_secret(),
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    token   = d["access_token"]
    expires = int(d.get("expires_in", 86400))
    expire  = time.time() + expires - 60
    _save_token_cache(token, expire)
    return token, expire


def _get_token() -> str:
    global _token_value, _token_expire
    # 인메모리 캐시 확인
    if _token_value and time.time() < _token_expire:
        return _token_value
    with _token_lock:
        if _token_value and time.time() < _token_expire:
            return _token_value
        # 파일 캐시 확인
        cached_token, cached_expire = _load_token_cache()
        if cached_token and time.time() < cached_expire:
            _token_value, _token_expire = cached_token, cached_expire
            return _token_value
        # 신규 발급
        _token_value, _token_expire = _fetch_token()
    return _token_value


# ── 가격 조회 ─────────────────────────────────────────────────────────────────
_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"


def _normalize_code(code: str) -> str:
    """'005930.KS' → '005930'  (6자리 제로패딩)"""
    return code.split(".")[0].zfill(6)


def _http_get(path: str, params: dict, headers: dict) -> dict:
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_base()}{path}?{qs}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def get_price(code: str) -> Dict[str, Any]:
    """종목 코드 실시간 현재가 조회.

    Returns:
        {
          "price":       80000,    # 현재가 (int)
          "change":      500,      # 전일대비 (int)
          "change_rate": 0.63,     # 전일대비율 (float, %)
          "volume":      1234567,  # 거래량
          "high":        80500,
          "low":         79000,
          "open":        79500,
          "code":        "005930",
          "source":      "KIS",
          "mock":        False,
          "available":   True,
        }

    On failure returns {"available": False, "error": "...", "code": code}.
    """
    if not is_available():
        return {"available": False, "error": "KIS 키 미설정 (.env 확인)", "code": code}

    isin = _normalize_code(code)
    try:
        token = _get_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey":        _app_key(),
            "appsecret":     _app_secret(),
            "tr_id":         "FHKST01010100",
            "custtype":      "P",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         isin,
        }
        raw = _http_get(_PRICE_PATH, params, headers)
        out = raw.get("output", {})

        def _int(k: str) -> int:
            try:
                return int(str(out.get(k, 0)).replace(",", ""))
            except Exception:
                return 0

        def _float(k: str) -> float:
            try:
                return float(str(out.get(k, 0)).replace(",", ""))
            except Exception:
                return 0.0

        return {
            "price":       _int("stck_prpr"),
            "change":      _int("prdy_vrss"),
            "change_rate": _float("prdy_ctrt"),
            "volume":      _int("acml_vol"),
            "high":        _int("stck_hgpr"),
            "low":         _int("stck_lwpr"),
            "open":        _int("stck_oprc"),
            "code":        isin,
            "source":      "KIS",
            "mock":        _is_mock(),
            "available":   True,
        }
    except Exception as e:
        return {"available": False, "error": str(e), "code": isin}


def get_prices(codes: list[str]) -> Dict[str, Dict[str, Any]]:
    """여러 종목 병렬 조회. {6자리코드: get_price(code)} 반환."""
    if not codes:
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    lock = threading.Lock()

    def _fetch(c: str) -> None:
        r = get_price(c)
        with lock:
            results[_normalize_code(c)] = r

    threads = [threading.Thread(target=_fetch, args=(c,), daemon=True) for c in codes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)
    return results


# ── 거래대금 순위 ─────────────────────────────────────────────────────────────
_VOLUME_RANK_PATH = "/uapi/domestic-stock/v1/quotations/volume-rank"


def _fetch_volume_rank_page(market_code: str) -> List[Dict[str, Any]]:
    """단일 시장(전체/KOSPI/KOSDAQ)에 대한 거래대금 순위 1페이지(최대 30종목) 조회."""
    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey":        _app_key(),
        "appsecret":     _app_secret(),
        "tr_id":         "FHPST01710000",
        "custtype":      "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE":  "J",
        "FID_COND_SCR_DIV_CODE":   "20171",
        "FID_INPUT_ISCD":          market_code,
        "FID_DIV_CLS_CODE":        "0",
        "FID_BLNG_CLS_CODE":       "0",
        "FID_TRGT_CLS_CODE":       "111111111",
        "FID_TRGT_EXLS_CLS_CODE":  "0000000000",
        "FID_INPUT_PRICE_1":       "",
        "FID_INPUT_PRICE_2":       "",
        "FID_VOL_CNT":             "",
        "FID_INPUT_DATE_1":        "",
    }
    raw = _http_get(_VOLUME_RANK_PATH, params, headers)
    return raw.get("output", []) or []


def get_volume_rank(top_n: int = 100) -> List[Dict[str, Any]]:
    """거래대금 상위 top_n 종목 조회.

    KIS volume-rank API는 호출당 최대 30종목만 반환하므로,
    top_n > 30 인 경우 KOSPI(0001)와 KOSDAQ(1001)을 별도 조회 후 병합한다.

    Returns:
        [{"code": "005930", "name": "삼성전자", "price": 80000,
          "volume": 1234567, "trade_amount": 98765432100}, ...]
    On failure returns [].
    """
    if not is_available():
        return []
    try:
        def _i(item: dict, k: str) -> int:
            try:
                return int(str(item.get(k, 0)).replace(",", ""))
            except Exception:
                return 0

        # 30종목 이하면 '전체' 시장 단일 호출로 충분
        if top_n <= 30:
            raw_items = _fetch_volume_rank_page("0000")
        else:
            # KOSPI + KOSDAQ 분리 조회 → 최대 60종목 확보 후 거래대금순 병합
            kospi  = _fetch_volume_rank_page("0001")
            kosdaq = _fetch_volume_rank_page("1001")
            merged: Dict[str, dict] = {}
            for item in list(kospi) + list(kosdaq):
                code = (item.get("mksc_shrn_iscd") or "").strip()
                if code and code not in merged:
                    merged[code] = item
            raw_items = sorted(
                merged.values(),
                key=lambda it: _i(it, "acml_tr_pbmn"),
                reverse=True,
            )

        result = []
        for item in raw_items[:top_n]:
            code = item.get("mksc_shrn_iscd", "").strip()
            if not code:
                continue
            result.append({
                "code":         code,
                "name":         item.get("hts_kor_isnm", "").strip(),
                "price":        _i(item, "stck_prpr"),
                "volume":       _i(item, "acml_vol"),
                "trade_amount": _i(item, "acml_tr_pbmn"),
            })
        return result
    except Exception:
        return []


# ── 투자자별 매매동향 ──────────────────────────────────────────────────────────
_INVESTOR_PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor"


def get_investor_trend(code: str) -> Dict[str, Any]:
    """투자자별 매매동향 조회 (외인/기관/프로그램 순매수량).

    Returns:
        {"foreign": int, "institution": int, "program": int, "available": bool}
        양수 = 순매수, 음수 = 순매도.
    On failure returns {"foreign": 0, "institution": 0, "program": 0, "available": False}.
    """
    if not is_available():
        return {"foreign": 0, "institution": 0, "program": 0, "available": False}

    isin = _normalize_code(code)
    try:
        token = _get_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey":        _app_key(),
            "appsecret":     _app_secret(),
            "tr_id":         "FHKST01010900",
            "custtype":      "P",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         isin,
        }
        raw = _http_get(_INVESTOR_PATH, params, headers)
        out = raw.get("output", {})

        def _int_field(obj: Any, k: str) -> int:
            try:
                v = str(obj.get(k, "")).replace(",", "").strip()
                return int(v) if v else 0
            except Exception:
                return 0

        # output은 일별 리스트 (index 0 = 오늘, 장중엔 빈 값일 수 있음)
        # 가장 최근 실제 데이터가 있는 행을 사용
        if isinstance(out, list):
            row = None
            for item in out:
                if str(item.get("frgn_ntby_qty", "")).strip():
                    row = item
                    break
            if row is None:
                row = out[0] if out else {}
            return {
                "foreign":     _int_field(row, "frgn_ntby_qty"),
                "institution": _int_field(row, "orgn_ntby_qty"),
                # 이 API에 프로그램 필드 없음 → 개인 역방향(순매도)을 대리 지표로 사용
                # 개인이 매도(-) = 외인+기관이 매수하는 전형적 수급 → 양수 처리
                "program":     -_int_field(row, "prsn_ntby_qty"),
                "available":   True,
            }

        # dict 응답인 경우 (구버전 호환)
        if isinstance(out, dict):
            return {
                "foreign":     _int_field(out, "frgn_ntby_qty"),
                "institution": _int_field(out, "orgn_ntby_qty"),
                "program":     -_int_field(out, "prsn_ntby_qty"),
                "available":   True,
            }

        return {"foreign": 0, "institution": 0, "program": 0, "available": False}
    except Exception:
        return {"foreign": 0, "institution": 0, "program": 0, "available": False}


# ── 분봉 차트 ─────────────────────────────────────────────────────────────────
_MINUTE_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"


def _fetch_1m_page(isin: str, hour_str: str) -> List[Dict[str, Any]]:
    """특정 시각 기준 1분봉 최대 30개 조회 (내부 헬퍼)."""
    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey":        _app_key(),
        "appsecret":     _app_secret(),
        "tr_id":         "FHKST03010200",
        "custtype":      "P",
    }
    params = {
        "FID_ETC_CLS_CODE":      "0",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":        isin,
        "FID_INPUT_HOUR_1":      hour_str,
        "FID_PW_DATA_INCU_YN":   "Y",
    }
    raw = _http_get(_MINUTE_CHART_PATH, params, headers)
    return raw.get("output2", [])


def _merge_candle_group(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """캔들 리스트를 하나의 집계 캔들로 병합 (오름차순 가정)."""
    def _i(item: dict, k: str) -> int:
        try:
            return int(str(item.get(k, 0)).replace(",", ""))
        except Exception:
            return 0

    opens  = [_i(c, "stck_oprc") for c in group]
    closes = [_i(c, "stck_prpr") for c in group]
    highs  = [_i(c, "stck_hgpr") for c in group]
    lows   = [_i(c, "stck_lwpr") for c in group if _i(c, "stck_lwpr") > 0]
    vols   = [_i(c, "cntg_vol") for c in group]
    last   = group[-1]

    return {
        "time":   str(last.get("stck_cntg_hour", "")).zfill(6),
        "date":   str(last.get("stck_bsop_date", "")),
        "open":   opens[0] if opens else 0,
        "high":   max(highs) if highs else 0,
        "low":    min(lows) if lows else 0,
        "close":  closes[-1] if closes else 0,
        "volume": sum(vols),
    }


def _aggregate_to_period(candles_1m: List[Dict[str, Any]], period: int) -> List[Dict[str, Any]]:
    """오름차순 1분봉 리스트를 period분봉으로 집계."""
    if not candles_1m:
        return []

    result: List[Dict[str, Any]] = []
    group: List[Dict[str, Any]] = []
    group_base: Optional[int] = None

    for candle in candles_1m:
        hour_str = str(candle.get("stck_cntg_hour", "090000")).zfill(6)
        h, m = int(hour_str[:2]), int(hour_str[2:4])
        total_min = h * 60 + m
        base_min = (total_min // period) * period

        if group_base is None:
            group_base = base_min

        if base_min != group_base:
            if group:
                result.append(_merge_candle_group(group))
            group = []
            group_base = base_min

        group.append(candle)

    if group:
        result.append(_merge_candle_group(group))

    return result


def get_minute_candles(code: str, period: int = 30, count: int = 20) -> List[Dict[str, Any]]:
    """분봉 데이터 조회 (period분봉, 최근 count개).

    내부적으로 1분봉 API를 반복 호출하여 period분봉으로 집계 반환.

    Returns:
        [{"time": "093000", "date": "20240101",
          "open": 79500, "high": 80500, "low": 79000,
          "close": 80000, "volume": 123456}, ...]
        시간 오름차순 정렬. On failure returns [].
    """
    if not is_available():
        return []

    isin = _normalize_code(code)
    try:
        needed_1m = period * (count + 2)  # 여유분 포함

        now = _dt.datetime.now()
        # 장 마감(15:30) 이후엔 15:30 기준으로 조회
        if now.hour > 15 or (now.hour == 15 and now.minute >= 30):
            cursor = now.replace(hour=15, minute=30, second=0, microsecond=0)
        else:
            cursor = now.replace(second=0, microsecond=0)

        all_1m: List[Dict[str, Any]] = []
        max_pages = min(20, (needed_1m // 30) + 3)

        for _ in range(max_pages):
            hour_str = cursor.strftime("%H%M%S")
            page = _fetch_1m_page(isin, hour_str)
            if not page:
                break
            all_1m.extend(page)
            if len(all_1m) >= needed_1m:
                break

            # 다음 페이지: 마지막 캔들 시각 1분 전
            last_h = str(page[-1].get("stck_cntg_hour", "090100")).zfill(6)
            h, m, s = int(last_h[:2]), int(last_h[2:4]), int(last_h[4:6])
            cursor = cursor.replace(hour=h, minute=m, second=s) - _dt.timedelta(minutes=1)
            if cursor.hour < 9:
                break
            time.sleep(0.05)  # rate limiting

        # 시간 오름차순 정렬
        all_1m.sort(key=lambda c: str(c.get("stck_cntg_hour", "")).zfill(6))

        # period분봉 집계 후 최근 count개 반환
        aggregated = _aggregate_to_period(all_1m, period)
        return aggregated[-count:] if len(aggregated) >= count else aggregated

    except Exception:
        return []


# ── 재무 데이터 (DCF 입력용) ─────────────────────────────────────────────────
_FINANCE_RATIO_PATH    = "/uapi/domestic-stock/v1/finance/financial-ratio"
_INCOME_STATEMENT_PATH = "/uapi/domestic-stock/v1/finance/income-statement"
_STOCK_INFO_PATH       = "/uapi/domestic-stock/v1/quotations/search-stock-info"

# 모듈 레벨 캐시 (프로세스 수명동안 12h)
_finance_cache: Dict[str, tuple[Dict[str, Any], float]] = {}
_FINANCE_TTL = 43200  # 12h
_finance_lock = threading.Lock()


def _to_float(x: Any) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0.0


def _fetch_finance_ratio(isin: str, mode: str = "ttm") -> Dict[str, float]:
    """국내주식 재무비율 — 최근 4분기 합산(TTM) EPS, 최신 분기 BPS/ROE/부채비율.

    mode="ttm": FID_DIV_CLS_CODE=0 (분기) → 최근 4분기 EPS 합산.
    mode="annual": FID_DIV_CLS_CODE=1 (연간) → 가장 최근 결산.
    """
    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey":        _app_key(),
        "appsecret":     _app_secret(),
        "tr_id":         "FHKST66430300",
        "custtype":      "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":         isin,
        "FID_DIV_CLS_CODE":       "1" if mode == "ttm" else "0",  # KIS: 0=년, 1=분기
    }
    raw = _http_get(_FINANCE_RATIO_PATH, params, headers)
    rows = raw.get("output", []) or []
    if not rows:
        return {}
    latest = rows[0]
    if mode == "ttm" and len(rows) >= 4:
        eps_ttm = sum(_to_float(r.get("eps")) for r in rows[:4])
        period_label = f"{rows[0].get('stac_yymm','')}~{rows[3].get('stac_yymm','')} (TTM)"
    else:
        eps_ttm = _to_float(latest.get("eps"))
        period_label = str(latest.get("stac_yymm", ""))
    return {
        "stac_yymm":  period_label,
        "eps":        eps_ttm,
        "bps":        _to_float(latest.get("bps")),
        "roe":        _to_float(latest.get("roe_val")),
        "debt_ratio": _to_float(latest.get("lblt_rate")),
        "rsrv_rate":  _to_float(latest.get("rsrv_rate")),
    }


def _fetch_income_statement(isin: str, mode: str = "ttm") -> Dict[str, float]:
    """국내주식 손익계산서 — TTM(최근 4분기 합산) 또는 연간 결산.

    KIS 응답 단위는 억원 → 원 환산 (×1e8).
    mode="ttm": 분기(FID_DIV_CLS_CODE=0) → 최근 4분기 영업이익/순이익 합산.
    mode="annual": 연간 → 가장 최근 결산.
    """
    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey":        _app_key(),
        "appsecret":     _app_secret(),
        "tr_id":         "FHKST66430200",
        "custtype":      "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":         isin,
        "FID_DIV_CLS_CODE":       "1" if mode == "ttm" else "0",  # KIS: 0=년, 1=분기
    }
    raw = _http_get(_INCOME_STATEMENT_PATH, params, headers)
    rows = raw.get("output", []) or []
    if not rows:
        return {}
    if mode == "ttm" and len(rows) >= 4:
        sample = rows[:4]
        op_inc = sum(_to_float(r.get("bsop_prti")) for r in sample) * 1e8
        net    = sum(_to_float(r.get("thtr_ntin")) for r in sample) * 1e8
        depr   = sum(_to_float(r.get("depr_cost")) for r in sample) * 1e8
        period_label = f"{sample[0].get('stac_yymm','')}~{sample[3].get('stac_yymm','')} (TTM)"
    else:
        latest = rows[0]
        op_inc = _to_float(latest.get("bsop_prti")) * 1e8
        net    = _to_float(latest.get("thtr_ntin")) * 1e8
        depr   = _to_float(latest.get("depr_cost")) * 1e8
        period_label = str(latest.get("stac_yymm", ""))
    # KIS depr_cost 는 종목 무관하게 동일 placeholder 가 자주 반환됨 → EBITDA 는 영업이익 단독을 보수적 프록시로 사용
    return {
        "stac_yymm":        period_label,
        "operating_income": op_inc,
        "net_income":       net,
        "depreciation":     depr,
        "ebitda":           op_inc,
    }


def _fetch_stock_info(isin: str) -> Dict[str, float]:
    """국내주식 현재가 조회의 lstn_stcn 필드로 상장주식수 획득."""
    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey":        _app_key(),
        "appsecret":     _app_secret(),
        "tr_id":         "FHKST01010100",
        "custtype":      "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":         isin,
    }
    raw = _http_get(_PRICE_PATH, params, headers)
    out = raw.get("output", {}) or {}
    return {
        "shares_outstanding": _to_float(out.get("lstn_stcn")),  # 주 단위
    }


def get_financials(code: str) -> Dict[str, Any]:
    """KIS Open API 재무 데이터 통합 조회 (EPS/BPS/ROE/영업이익/EBITDA/발행주식수).

    Returns:
        {
          "eps":                float,   # 원/주
          "bps":                float,   # 원/주
          "roe":                float,   # %
          "debt_ratio":         float,   # %
          "operating_income":   float,   # 원 (총액)
          "net_income":         float,   # 원
          "depreciation":       float,   # 원
          "ebitda":             float,   # 원
          "shares_outstanding": float,   # 주
          "fiscal_period":      str,     # YYYYMM
          "source":             "KIS",
          "available":          bool,
        }
    """
    if not is_available():
        return {"available": False, "error": "KIS 키 미설정"}

    isin = _normalize_code(code)
    now  = time.time()
    with _finance_lock:
        cached = _finance_cache.get(isin)
        if cached and (now - cached[1]) < _FINANCE_TTL:
            return cached[0]

    result: Dict[str, Any] = {"source": "KIS", "available": False}
    try:
        # 세 엔드포인트 직렬 호출 (KIS rate-limit 보호)
        try:
            result.update(_fetch_finance_ratio(isin))
        except Exception as e:
            result["_err_ratio"] = str(e)
        try:
            result.update(_fetch_income_statement(isin))
        except Exception as e:
            result["_err_income"] = str(e)
        try:
            result.update(_fetch_stock_info(isin))
        except Exception as e:
            result["_err_stockinfo"] = str(e)

        # shares 폴백: 직접 조회 실패 시 net_income / EPS 로 역산
        if (not result.get("shares_outstanding")
                and result.get("net_income") and result.get("eps")):
            try:
                result["shares_outstanding"] = result["net_income"] / result["eps"]
                result["_shares_derived"] = True
            except Exception:
                pass

        # 최소한 EPS/BPS 또는 영업이익 중 하나라도 있어야 사용 가능
        if result.get("eps") or result.get("bps") or result.get("operating_income"):
            result["available"] = True
            result["fiscal_period"] = result.get("stac_yymm", "")

        with _finance_lock:
            _finance_cache[isin] = (result, now)
    except Exception as e:
        result["error"] = str(e)
    return result


# ── 셀프테스트 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[kis_api] available={is_available()} mock={_is_mock()}")
    if is_available():
        r = get_price("005930")
        print("[kis_api] 삼성전자:", r)
        r2 = get_price("000660")
        print("[kis_api] SK하이닉스:", r2)
        fin = get_financials("005930")
        print("[kis_api] 삼성전자 재무:", fin)
    else:
        print("[kis_api] .env 파일에서 KIS 키를 읽지 못했습니다.")
