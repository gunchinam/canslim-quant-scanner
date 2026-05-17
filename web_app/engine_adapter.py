"""
engine_adapter.py — quant_nexus_v20.py 엔진을 tkinter 없이 사용하는 어댑터
Flask 웹앱이 이 클래스를 통해 스캔 기능을 호출한다.
"""
import sys
import os
import threading
import logging
import concurrent.futures
from collections import OrderedDict

# 프로젝트 경로 추가 (quant_nexus_v20.py가 있는 디렉토리)
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

# quant_nexus_v20 import
# Windows에서 tkinter는 import만으로 GUI를 띄우지 않음 — 안전하게 import 가능
import quant_nexus_v20 as _qn


class ScanAdapter:
    """
    QuantNexusApp.analyze_ticker()를 tkinter 없이 실행하는 어댑터.
    analyze_ticker가 self.*로 접근하는 모든 속성을 직접 보유하여
    unbound method 호출(_qn.QuantNexusApp.analyze_ticker(self, ticker))이 동작한다.
    """

    def __init__(self, market: str = "US", strategy: str = "BALANCED") -> None:
        self._market = market
        self._strategy = strategy

        # ── analyze_ticker가 사용하는 속성 (QuantNexusApp 인터페이스 호환) ──
        self.cache          = _qn.DataCache()
        self.engine         = _qn.WallStreetQuantStrategies()
        self.vix_value      = 20.0
        self._scan_strategy = strategy
        self._scan_market   = market
        self._stats_lock    = threading.Lock()
        self.stats          = {
            "cache_hits": 0, "cache_misses": 0,
            "scanned": 0, "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0,
        }
        self._naver_target_cache: dict        = {}
        self._naver_fund_cache:   dict        = {}
        self._committee_cache:    OrderedDict = OrderedDict()
        self._committee_cache_max              = 1000

        # ── 네이버 캐시 파일 경로 (원본 엔진과 동일 위치) ──
        self._naver_cache_path = os.path.join(_BASE, "naver_target_cache.pkl")
        self._naver_fund_cache_path = os.path.join(_BASE, "naver_fund_cache.pkl")
        # 기존 캐시 로드
        _qn.QuantNexusApp._load_naver_cache(self)
        _qn.QuantNexusApp._load_naver_fund_cache(self)

        # ── 섹터·종목 데이터 초기화 ──────────────────────────────────────────
        _qn.QuantNexusApp._init_sector_data(self)
        # 클래스 속성 인스턴스에 직접 복사 (_analyze_ticker에서 self.*로 접근)
        self.KR_NAMES = _qn.QuantNexusApp.KR_NAMES
        self.US_DESC  = _qn.QuantNexusApp.US_DESC
        self.KR_DESC  = _qn.QuantNexusApp.KR_DESC

        # market별 flat 섹터 dict {섹터명: [ticker, ...]} 빌드
        self._sectors: dict[str, list[str]] = {}
        self._build_sectors()

    # ── 내부 초기화 ───────────────────────────────────────────────────────

    def _build_sectors(self) -> None:
        raw = self.kr_sectors if self._market == "KR" else self.us_sectors
        sub_kr = getattr(self, 'us_sector_labels_kr', {}) if self._market != "KR" else {}
        for cat_data in raw.values():
            for subcat, tickers in cat_data.items():
                self._sectors[sub_kr.get(subcat, subcat)] = tickers

    # ── QuantNexusApp이 사용하는 메서드 (tkinter 콜백 대체) ──────────────

    def _log(self, msg: str) -> None:
        logging.debug("[ScanAdapter] %s", msg)

    def _fetch_naver_target(self, ticker: str):
        """(DEPRECATED) DCF 목표가로 대체됨 — 호환성 유지용."""
        return _qn.QuantNexusApp._fetch_naver_target(self, ticker)

    def _fetch_naver_fundamentals(self, ticker: str):
        """네이버 재무 데이터 — 원본 엔진 메서드 위임."""
        return _qn.QuantNexusApp._fetch_naver_fundamentals(self, ticker)

    def _save_naver_cache(self):
        """(DEPRECATED) DCF 목표가로 대체됨 — 호환성 유지용."""
        _qn.QuantNexusApp._save_naver_cache(self)

    def _save_naver_fund_cache(self):
        """네이버 재무 캐시 저장 — 원본 엔진 메서드 위임."""
        _qn.QuantNexusApp._save_naver_fund_cache(self)

    # ── 공개 API ─────────────────────────────────────────────────────────

    def get_sectors(self) -> dict[str, list[str]]:
        """market별 섹터→종목 매핑 반환 (flat)."""
        return self._sectors

    def get_sector_groups(self) -> dict[str, list[str]]:
        """카테고리 → 서브섹터 리스트 반환 (사이드바 그룹 표시용)."""
        raw = self.kr_sectors if self._market == "KR" else self.us_sectors
        if self._market == "KR":
            return {cat: list(subsectors.keys()) for cat, subsectors in raw.items()}
        cat_kr = getattr(self, 'us_sector_category_kr', {})
        sub_kr = getattr(self, 'us_sector_labels_kr', {})
        result = {}
        for cat, subsectors in raw.items():
            translated_cat = cat
            for en, kr in cat_kr.items():
                if en in cat:
                    translated_cat = cat.replace(en, kr)
                    break
            result[translated_cat] = [sub_kr.get(s, s) for s in subsectors.keys()]
        return result

    def analyze_ticker(self, ticker: str) -> dict | None:
        """단일 종목 분석 — QuantNexusApp.analyze_ticker 직접 위임."""
        return _qn.QuantNexusApp._analyze_ticker(self, ticker)

    def scan_sector(self, sector: str, *, max_workers: int = 8) -> list[dict]:
        """특정 섹터 종목을 병렬 분석 후 TotalScore 내림차순 반환."""
        tickers = self._sectors.get(sector, [])
        results: list[dict] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(self.analyze_ticker, t): t for t in tickers}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    r = fut.result()
                    if r:
                        r["Sector"] = sector
                        results.append(r)
                except Exception as e:
                    logging.error("scan_sector error: %s", e)
        results.sort(key=lambda x: x.get("TotalScore", 0), reverse=True)
        return results

    def scan_all(self, *, max_workers: int = 8) -> list[dict]:
        """전체 섹터 종목을 병렬 분석 (중복 ticker 제거) 후 TotalScore 내림차순 반환."""
        ticker_sector: dict[str, str] = {}
        for sector, tickers in self._sectors.items():
            for t in tickers:
                if t not in ticker_sector:
                    ticker_sector[t] = sector

        results: list[dict] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(self.analyze_ticker, t): (t, s)
                for t, s in ticker_sector.items()
            }
            for fut in concurrent.futures.as_completed(futures):
                ticker, sector = futures[fut]
                try:
                    r = fut.result()
                    if r:
                        r.setdefault("Sector", sector)
                        results.append(r)
                except Exception as e:
                    logging.error("scan_all [%s] error: %s", ticker, e)
        results.sort(key=lambda x: x.get("TotalScore", 0), reverse=True)
        return results
