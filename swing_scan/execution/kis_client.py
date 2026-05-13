"""execution/kis_client.py
KIS (한국투자증권) REST API 클라이언트

기능:
  - OAuth2 access token 발급/갱신
  - 현재가 조회
  - 시장가/지정가 주문 (매수/매도)
  - 주문 취소
  - 잔고/보유종목 조회

설정: .env 파일의 APP_KEY, APP_SECRET, ACCOUNT_NO 사용
실전/모의 자동 전환: IS_MOCK=true/false
"""
from __future__ import annotations

import os
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from config.api_keys import get_kis_keys

# 스크립트 실행 위치에 관계없이 항상 프로젝트 루트의 .env 로드
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# ── 환경변수 ───────────────────────────────────────────────────────────────
_KIS_KEYS = get_kis_keys()
APP_KEY = _KIS_KEYS.get("app_key", "")
APP_SECRET = _KIS_KEYS.get("app_secret", "")
ACCOUNT_NO = _KIS_KEYS.get("account_no", "")
ACCOUNT_CODE = str(_KIS_KEYS.get("account_code", "01") or "01").zfill(2)
IS_MOCK = bool(_KIS_KEYS.get("is_mock", False))

# ── 엔드포인트 ─────────────────────────────────────────────────────────────
BASE_URL_REAL = "https://openapi.koreainvestment.com:9443"
BASE_URL_MOCK = "https://openapivts.koreainvestment.com:29443"
BASE_URL = BASE_URL_MOCK if IS_MOCK else BASE_URL_REAL

# ── TR ID (실전/모의 구분) ──────────────────────────────────────────────────
TR_BUY_CASH  = "VTTC0802U" if IS_MOCK else "TTTC0802U"   # 주식 매수
TR_SELL_CASH = "VTTC0801U" if IS_MOCK else "TTTC0801U"   # 주식 매도
TR_CANCEL    = "VTTC0804U" if IS_MOCK else "TTTC0804U"   # 주문 취소 (0803=정정, 0804=취소)

_ACCOUNT_NO_DIGITS = "".join(ch for ch in ACCOUNT_NO if ch.isdigit())
_ACCT_PREFIX = _ACCOUNT_NO_DIGITS[:8] if len(_ACCOUNT_NO_DIGITS) >= 8 else _ACCOUNT_NO_DIGITS
_ACCT_SUFFIX = _ACCOUNT_NO_DIGITS[8:10] if len(_ACCOUNT_NO_DIGITS) >= 10 else ACCOUNT_CODE

_TOKEN_CACHE_PATH = _PROJECT_ROOT / ".omc/kis_token.json"
_ACCOUNT_CACHE_MODE = "mock" if IS_MOCK else "real"
_ACCOUNT_CACHE_KEY = f"{_ACCOUNT_CACHE_MODE}_{_ACCT_PREFIX}_{_ACCT_SUFFIX}"
_ACCOUNT_VALUE_CACHE_PATH = _PROJECT_ROOT / f".omc/kis_account_value_{_ACCOUNT_CACHE_KEY}.json"


class KISClient:
    """KIS Open API REST 클라이언트."""

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._token_lock = threading.Lock()
        self._last_account_value: float = 0.0
        self._v2_client = None
        self._load_cached_token()
        self._load_cached_account_value()

    # ── 토큰 관리 ─────────────────────────────────────────────────────────

    def _load_cached_token(self):
        if _TOKEN_CACHE_PATH.exists():
            try:
                data = json.loads(_TOKEN_CACHE_PATH.read_text())
                expires = datetime.fromisoformat(data["expires"])
                if expires > datetime.now() + timedelta(minutes=5):
                    self._access_token = data["token"]
                    self._token_expires = expires
                    logger.debug("캐시 토큰 로드 완료")
            except Exception:
                pass

    def _save_token_cache(self):
        _TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE_PATH.write_text(json.dumps({
            "token": self._access_token,
            "expires": self._token_expires.isoformat(),
        }))

    def _load_cached_account_value(self):
        if _ACCOUNT_VALUE_CACHE_PATH.exists():
            try:
                data = json.loads(_ACCOUNT_VALUE_CACHE_PATH.read_text())
                if (
                    str(data.get("account_prefix", "")) != _ACCT_PREFIX
                    or str(data.get("account_suffix", "")) != _ACCT_SUFFIX
                    or bool(data.get("is_mock", False)) != IS_MOCK
                ):
                    return
                value = float(data.get("value", 0) or 0)
                if value > 0:
                    self._last_account_value = value
            except Exception:
                pass

    def _save_cached_account_value(self, value: float):
        if value <= 0:
            return
        self._last_account_value = value
        _ACCOUNT_VALUE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ACCOUNT_VALUE_CACHE_PATH.write_text(json.dumps({
            "value": value,
            "saved_at": datetime.now().isoformat(),
            "account_prefix": _ACCT_PREFIX,
            "account_suffix": _ACCT_SUFFIX,
            "is_mock": IS_MOCK,
        }))

    def _fallback_account_value(self, reason: str) -> float:
        if self._last_account_value > 0:
            logger.warning(
                "[계좌가치] %s. 마지막 정상 계좌가치 %.0f원을 폴백으로 사용합니다.",
                reason,
                self._last_account_value,
            )
            return self._last_account_value
        return 0.0

    def _balance_params(self) -> dict:
        return {
            "CANO": _ACCT_PREFIX,
            "ACNT_PRDT_CD": _ACCT_SUFFIX,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

    def _get_v2_client(self):
        if self._v2_client is None:
            from api.kis_api_v2 import KISApiV2

            self._v2_client = KISApiV2(
                app_key=APP_KEY,
                app_secret=APP_SECRET,
                account_no=_ACCT_PREFIX,
                account_code=_ACCT_SUFFIX,
                is_mock=IS_MOCK,
            )
        return self._v2_client

    def _get_v2_balance_snapshot(self) -> Optional[dict]:
        try:
            balance = self._get_v2_client().get_balance()
            if isinstance(balance, dict):
                return balance
        except Exception as e:
            logger.warning(f"[KIS:v2] 잔고 조회 fallback 실패: {e}")
        return None

    def get_access_token(self) -> str:
        with self._token_lock:
            if self._access_token and self._token_expires and datetime.now() < self._token_expires:
                return self._access_token

            if not APP_KEY or not APP_SECRET:
                raise RuntimeError(
                    "KIS APP_KEY / APP_SECRET 미설정. "
                    f"프로젝트 루트 .env 파일을 확인하세요: {_PROJECT_ROOT / '.env'}"
                )

            url = f"{BASE_URL}/oauth2/tokenP"
            body = {
                "grant_type": "client_credentials",
                "appkey": APP_KEY,
                "appsecret": APP_SECRET,
            }
            resp = requests.post(url, json=body, timeout=10)
            if resp.status_code == 403:
                mode = "모의투자" if IS_MOCK else "실전"
                raise RuntimeError(
                    f"KIS 토큰 발급 실패 (403 Forbidden) — {mode} 모드\n"
                    f"  원인 1: 실전 API 사용 IP 미등록 → KIS 포털(https://securities.koreainvestment.com) > 트레이딩센터 > Open API > IP 등록\n"
                    f"  원인 2: 앱키가 {'실전' if IS_MOCK else '모의투자'}용 → .env의 IS_MOCK 설정 확인\n"
                    f"  현재: IS_MOCK={IS_MOCK}, APP_KEY={APP_KEY[:6]}***"
                )
            resp.raise_for_status()
            data = resp.json()

            self._access_token = data["access_token"]
            expires_in = int(data.get("expires_in", 86400))
            self._token_expires = datetime.now() + timedelta(seconds=expires_in - 300)
            self._save_token_cache()
            logger.info("KIS 토큰 발급 완료")
            return self._access_token

    def _headers(self, tr_id: str, tr_cont: str = "") -> dict:
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P",
        }

    # ── 현재가 조회 ───────────────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> Optional[float]:
        """현재가(stck_prpr) 조회."""
        price, _ = self.get_price_and_limit(ticker)
        return price

    def get_price_and_limit(self, ticker: str):
        """현재가(stck_prpr) + 상한가(stck_uplmt) 동시 조회.

        Returns:
            (current_price, upper_limit_price) — 실패 시 (None, None)
        """
        url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._headers("FHKST01010100")
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                logger.warning(f"KIS API 에러 [get_price_and_limit]: {data.get('msg1', 'unknown')}")
                return None, None
            out = data.get("output", {})
            price = float(out.get("stck_prpr", "0") or "0") or None
            uplmt = float(out.get("stck_uplmt", "0") or "0") or None
            return price, uplmt
        except Exception as e:
            logger.error(f"현재가/상한가 조회 실패 {ticker}: {e}")
            return None, None

    # ── 주문 ──────────────────────────────────────────────────────────────

    def place_order(
        self,
        ticker: str,
        side: str,          # "BUY" or "SELL"
        qty: int,
        price: int = 0,     # 0이면 시장가
        order_type: str = "01",  # 01=시장가, 00=지정가
    ) -> dict:
        """주문 실행.

        Returns:
            {"success": bool, "order_no": str, "msg": str}
        """
        if not APP_KEY or not APP_SECRET or not ACCOUNT_NO:
            return {"success": False, "order_no": "", "msg": "API 키 미설정"}

        tr_id = TR_BUY_CASH if side == "BUY" else TR_SELL_CASH
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

        body = {
            "CANO":         _ACCT_PREFIX,
            "ACNT_PRDT_CD": _ACCT_SUFFIX,
            "PDNO":         ticker,
            "ORD_DVSN":     order_type,
            "ORD_QTY":      str(qty),
            "ORD_UNPR":     str(price) if order_type == "00" else "0",
        }

        mode_str = "[모의]" if IS_MOCK else "[실전]"
        logger.info(f"{mode_str} {side} {ticker} {qty}주 price={price}")

        for _attempt in range(2):
            try:
                resp = requests.post(
                    url,
                    headers=self._headers(tr_id),
                    json=body,
                    timeout=10,
                )
                # raise_for_status 전에 JSON 응답을 먼저 읽어 EGW 코드 확인
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                if resp.status_code >= 400:
                    msg_cd = data.get("msg_cd", "")
                    if msg_cd == "EGW00123" and _attempt == 0:
                        # 토큰 만료 감지 → 강제 무효화 후 1회 재시도
                        logger.warning("토큰 만료(EGW00123) 감지 — 토큰 재발급 후 재시도")
                        with self._token_lock:
                            self._access_token = None
                            self._token_expires = None
                        if _TOKEN_CACHE_PATH.exists():
                            _TOKEN_CACHE_PATH.unlink(missing_ok=True)
                        continue
                    raise requests.HTTPError(
                        f"{resp.status_code} {data.get('msg1', resp.reason)}",
                        response=resp,
                    )

                rt_cd = data.get("rt_cd", "9")
                msg   = data.get("msg1", "")
                order_no = data.get("output", {}).get("ODNO", "")

                if rt_cd == "0":
                    logger.info(f"  주문 성공: ODNO={order_no}")
                    return {"success": True, "order_no": order_no, "msg": msg}
                else:
                    logger.error(f"  주문 실패: {rt_cd} {msg}")
                    return {"success": False, "order_no": "", "msg": msg}

            except requests.HTTPError as e:
                logger.error(f"주문 요청 오류: {e}")
                return {"success": False, "order_no": "", "msg": str(e)}
            except Exception as e:
                logger.error(f"주문 요청 오류: {e}")
                return {"success": False, "order_no": "", "msg": str(e)}
        return {"success": False, "order_no": "", "msg": "토큰 재발급 후 재시도 실패"}

    def buy_market(self, ticker: str, qty: int) -> dict:
        return self.place_order(ticker, "BUY", qty, order_type="01")

    def sell_market(self, ticker: str, qty: int) -> dict:
        return self.place_order(ticker, "SELL", qty, order_type="01")

    def buy_limit(self, ticker: str, qty: int, price: int) -> dict:
        return self.place_order(ticker, "BUY", qty, price=price, order_type="00")

    def sell_limit(self, ticker: str, qty: int, price: int) -> dict:
        return self.place_order(ticker, "SELL", qty, price=price, order_type="00")

    # ── KRX 호가단위 / 지정가 헬퍼 ────────────────────────────────────────

    _TICK_SIZES = [
        (2_000,          1),
        (5_000,          5),
        (20_000,        10),
        (50_000,        50),
        (200_000,      100),
        (500_000,      500),
        (float("inf"), 1000),
    ]

    @classmethod
    def get_tick_size(cls, price: int) -> int:
        """KRX 호가단위 반환."""
        for limit, tick in cls._TICK_SIZES:
            if price < limit:
                return tick
        return 1000

    def get_ask1(self, ticker: str) -> int:
        """매도 1호가(ask1) 반환. 실패 시 현재가로 폴백, 조회 불가 시 0."""
        try:
            url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
            headers = self._headers("FHKST01010200")
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
            }
            resp = requests.get(url, headers=headers, params=params, timeout=8)
            data = resp.json()
            if resp.status_code == 200 and data.get("rt_cd") == "0":
                ask1 = int(data.get("output1", {}).get("askp1", 0) or 0)
                if ask1 > 0:
                    return ask1
        except Exception as e:
            logger.warning(f"[KIS] get_ask1 실패 ({ticker}): {e}")
        price = self.get_current_price(ticker)
        return int(price) if price else 0

    def cancel_order(self, order_no: str, ticker: str, qty: int, price: int) -> dict:
        """지정가 주문 취소."""
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        body = {
            "CANO":               _ACCT_PREFIX,
            "ACNT_PRDT_CD":       _ACCT_SUFFIX,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO":          order_no,
            "ORD_DVSN":           "00",
            "RVSE_CNCL_DVSN_CD": "02",   # 02=취소
            "ORD_QTY":            str(qty),
            "ORD_UNPR":           str(price),
            "PDNO":               ticker,
            "MGCO_APTM_ODNO":     "",
            "QTY_ALL_ORD_YN":     "Y",
        }
        try:
            resp = requests.post(
                url, headers=self._headers(TR_CANCEL), json=body, timeout=10
            )
            data = resp.json()
            if data.get("rt_cd") == "0":
                logger.info(f"[KIS] 주문취소 성공: {order_no}")
                return {"success": True}
            logger.warning(f"[KIS] 주문취소 실패: {data.get('msg1', '')}")
            return {"success": False, "msg": data.get("msg1", "")}
        except Exception as e:
            logger.error(f"[KIS] cancel_order 오류: {e}")
            return {"success": False, "msg": str(e)}

    def get_unfilled_qty(self, order_no: str, ticker: str) -> int:
        """미체결 잔량 조회. 전량 체결 시 0, 목록 없으면 0, 조회 실패 시 -1."""
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        tr_id = "VTTC8036R" if IS_MOCK else "TTTC8036R"
        params = {
            "CANO":             _ACCT_PREFIX,
            "ACNT_PRDT_CD":     _ACCT_SUFFIX,
            "CTX_AREA_FK100":   "",
            "CTX_AREA_NK100":   "",
            "INQR_DVSN_1":      "0",
            "INQR_DVSN_2":      "0",
        }
        try:
            resp = requests.get(
                url, headers=self._headers(tr_id), params=params, timeout=10
            )
            data = resp.json()
            if data.get("rt_cd") == "0":
                for item in data.get("output", []):
                    if item.get("ODNO", "") == order_no and item.get("PDNO", "") == ticker:
                        return int(item.get("RMND_QTY", "0") or "0")
                return 0  # 목록에 없으면 전량 체결
        except Exception as e:
            logger.warning(f"[KIS] get_unfilled_qty 오류: {e}")
        return -1

    # ── 잔고 조회 ─────────────────────────────────────────────────────────

    def get_balance(self) -> list[dict]:
        """보유 종목 목록 조회 (output1)."""
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if IS_MOCK else "TTTC8434R"
        headers = self._headers(tr_id)
        params = self._balance_params()
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                logger.warning(f"KIS API 에러 [get_balance]: {data.get('msg1', 'unknown')}")
                snapshot = self._get_v2_balance_snapshot()
                if snapshot:
                    holdings = snapshot.get("holdings", [])
                    return [
                        {
                            "pdno": item.get("code", ""),
                            "prdt_name": item.get("name", ""),
                            "hldg_qty": str(item.get("quantity", 0)),
                            "pchs_avg_pric": str(item.get("avg_price", 0)),
                            "prpr": str(item.get("current_price", 0)),
                            "evlu_pfls_amt": str(item.get("profit", 0)),
                            "evlu_pfls_rt": str(item.get("profit_rate", 0)),
                            "evlu_amt": str(item.get("value", 0)),
                        }
                        for item in holdings
                    ]
                return []
            return data.get("output1", [])
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            snapshot = self._get_v2_balance_snapshot()
            if snapshot:
                holdings = snapshot.get("holdings", [])
                return [
                    {
                        "pdno": item.get("code", ""),
                        "prdt_name": item.get("name", ""),
                        "hldg_qty": str(item.get("quantity", 0)),
                        "pchs_avg_pric": str(item.get("avg_price", 0)),
                        "prpr": str(item.get("current_price", 0)),
                        "evlu_pfls_amt": str(item.get("profit", 0)),
                        "evlu_pfls_rt": str(item.get("profit_rate", 0)),
                        "evlu_amt": str(item.get("value", 0)),
                    }
                    for item in holdings
                ]
            return []

    def get_account_value(self) -> float:
        """계좌 총 평가금액 조회 (output2.tot_evlu_amt)."""
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if IS_MOCK else "TTTC8434R"
        headers = self._headers(tr_id)
        params = self._balance_params()
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                return self._fallback_account_value(
                    f"KIS API 에러 [get_account_value]: {data.get('msg1', 'unknown')}"
                )
            output2 = data.get("output2", [])
            if output2:
                summary = output2[0] if isinstance(output2, list) else output2
                val = float(summary.get("tot_evlu_amt", 0) or 0)
                if val > 0:
                    self._save_cached_account_value(val)
                    return val
                # tot_evlu_amt가 0이면 순자산/예수금으로 fallback (장중 서킷브레이커 등 특수상황)
                for key in ("nass_amt", "dnca_tot_amt"):
                    val = float(summary.get(key, 0) or 0)
                    if val > 0:
                        logger.info(f"[계좌가치] tot_evlu_amt=0, fallback {key}={val:,.0f}원 사용")
                        self._save_cached_account_value(val)
                        return val
        except Exception as e:
            snapshot = self._get_v2_balance_snapshot()
            if snapshot:
                for key in ("total_assets", "total_equity", "ord_psbl_cash", "cash"):
                    val = float(snapshot.get(key, 0) or 0)
                    if val > 0:
                        logger.info(f"[계좌가치] v2 fallback {key}={val:,.0f}원 사용")
                        self._save_cached_account_value(val)
                        return val
            return self._fallback_account_value(f"계좌 총액 조회 실패: {e}")
        return self._fallback_account_value("계좌 총액 응답에 사용 가능한 평가금액이 없습니다")


# ── 편의 함수 ──────────────────────────────────────────────────────────────
    def get_orderable_cash(self) -> float:
        """Return immediately orderable KRW for new entries."""
        snapshot = self._get_v2_balance_snapshot()
        if isinstance(snapshot, dict):
            for key in ("ord_psbl_cash", "cash"):
                val = float(snapshot.get(key, 0) or 0)
                if val > 0:
                    return val

        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if IS_MOCK else "TTTC8434R"
        headers = self._headers(tr_id)
        params = self._balance_params()
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                logger.warning("orderable cash lookup failed: %s", data.get("msg1", "unknown"))
                return 0.0
            output2 = data.get("output2", [])
            if output2:
                summary = output2[0] if isinstance(output2, list) else output2
                for key in ("ord_psbl_cash", "dnca_tot_amt"):
                    val = float(summary.get(key, 0) or 0)
                    if val > 0:
                        return val
        except Exception as e:
            logger.warning("orderable cash lookup failed: %s", e)
        return 0.0

_client: Optional[KISClient] = None


def get_client() -> KISClient:
    global _client
    if _client is None:
        _client = KISClient()
    return _client


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = KISClient()
    token = client.get_access_token()
    print(f"토큰 발급 성공: {token[:20]}...")
    mode = "모의" if IS_MOCK else "실전"
    print(f"모드: {mode}, 계좌: {_ACCT_PREFIX}-{_ACCT_SUFFIX}")
