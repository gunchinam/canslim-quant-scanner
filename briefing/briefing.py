"""
📈 강세 종목 스크리닝 & 텔레그램 자동 브리핑
================================================
대상  : KOSPI + KOSDAQ + S&P500 + NASDAQ 100
조건  : 전일 대비 상승률 상위 30개
필터  : 국내 거래대금 100억↑ / 미국 5천만 달러↑
발송  : 텔레그램 봇 (HTML 파싱)
스케줄: GitHub Actions cron (매일 16:30 KST, 평일)
LLM  : Groq API (llama-3.3-70b-versatile) — 시황 한줄 요약

환경변수 (GitHub Secrets):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  GROQ_API_KEY
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from io import StringIO

# ── 로깅 설정 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("briefing.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


# ═══════════════════════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════════════════════

def _trading_date() -> str:
    """
    실행 시각 기준으로 '사용할 날짜' 계산.
    - 16:00 이전  → 직전 영업일 (오늘 장 아직 안 끝남)
    - 16:00 이후  → 오늘 날짜
    - 주말은 건너뜀
    """
    now = datetime.now(KST)
    if now.hour < 16:
        dt = now - timedelta(days=1)
    else:
        dt = now
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    result = dt.strftime("%Y%m%d")
    log.info("기준 날짜: %s", result)
    return result


# ═══════════════════════════════════════════════════════════
# 1단계: 강세 종목 스크리닝
# ═══════════════════════════════════════════════════════════

# 주요 KOSPI + KOSDAQ 종목 (ticker → (name, market))
_KR_TICKERS: dict[str, tuple[str, str]] = {
    # KOSPI
    "005930.KS": ("삼성전자",     "KOSPI"), "000660.KS": ("SK하이닉스",      "KOSPI"),
    "207940.KS": ("삼성바이오",   "KOSPI"), "005380.KS": ("현대차",          "KOSPI"),
    "000270.KS": ("기아",         "KOSPI"), "373220.KS": ("LG에너지솔루션",  "KOSPI"),
    "006400.KS": ("삼성SDI",      "KOSPI"), "051910.KS": ("LG화학",          "KOSPI"),
    "035420.KS": ("NAVER",        "KOSPI"), "005490.KS": ("POSCO홀딩스",     "KOSPI"),
    "012330.KS": ("현대모비스",   "KOSPI"), "068270.KS": ("셀트리온",        "KOSPI"),
    "105560.KS": ("KB금융",       "KOSPI"), "055550.KS": ("신한지주",        "KOSPI"),
    "028260.KS": ("삼성물산",     "KOSPI"), "066570.KS": ("LG전자",          "KOSPI"),
    "003550.KS": ("LG",           "KOSPI"), "017670.KS": ("SK텔레콤",        "KOSPI"),
    "030200.KS": ("KT",           "KOSPI"), "086790.KS": ("하나금융지주",    "KOSPI"),
    "316140.KS": ("우리금융지주", "KOSPI"), "034730.KS": ("SK",              "KOSPI"),
    "011200.KS": ("HMM",          "KOSPI"), "010130.KS": ("고려아연",        "KOSPI"),
    "009150.KS": ("삼성전기",     "KOSPI"), "018260.KS": ("삼성SDS",         "KOSPI"),
    "000810.KS": ("삼성화재",     "KOSPI"), "003490.KS": ("대한항공",        "KOSPI"),
    "090430.KS": ("아모레퍼시픽", "KOSPI"), "036570.KS": ("엔씨소프트",      "KOSPI"),
    "035720.KS": ("카카오",       "KOSPI"), "259960.KS": ("크래프톤",        "KOSPI"),
    "293490.KS": ("카카오뱅크",   "KOSPI"), "352820.KS": ("하이브",          "KOSPI"),
    "003670.KS": ("포스코퓨처엠", "KOSPI"), "012450.KS": ("한화에어로스페이스","KOSPI"),
    "042700.KS": ("한미반도체",   "KOSPI"), "000100.KS": ("유한양행",        "KOSPI"),
    "267250.KS": ("현대중공업",   "KOSPI"), "329180.KS": ("HD현대중공업",    "KOSPI"),
    "009540.KS": ("HD한국조선해양","KOSPI"), "010950.KS": ("S-Oil",           "KOSPI"),
    "097950.KS": ("CJ제일제당",   "KOSPI"), "034020.KS": ("두산에너빌리티",  "KOSPI"),
    "000720.KS": ("현대건설",     "KOSPI"), "078930.KS": ("GS",              "KOSPI"),
    "004020.KS": ("현대제철",     "KOSPI"), "096770.KS": ("SK이노베이션",    "KOSPI"),
    "251270.KS": ("넷마블",       "KOSPI"), "032830.KS": ("삼성생명",        "KOSPI"),
    "024110.KS": ("기업은행",     "KOSPI"), "015760.KS": ("한국전력",        "KOSPI"),
    "011170.KS": ("롯데케미칼",   "KOSPI"), "139480.KS": ("이마트",          "KOSPI"),
    "047050.KS": ("포스코인터내셔널","KOSPI"), "011790.KS": ("SKC",           "KOSPI"),
    "051900.KS": ("LG생활건강",   "KOSPI"), "071050.KS": ("한국금융지주",    "KOSPI"),
    "161390.KS": ("한국타이어",   "KOSPI"), "001040.KS": ("CJ",              "KOSPI"),
    "375500.KS": ("DL이앤씨",     "KOSPI"), "302440.KS": ("SK바이오사이언스","KOSPI"),
    "326030.KS": ("SK바이오팜",   "KOSPI"), "180640.KS": ("한진칼",          "KOSPI"),
    "000880.KS": ("한화",         "KOSPI"), "009830.KS": ("한화솔루션",      "KOSPI"),
    "003410.KS": ("쌍용C&E",      "KOSPI"), "138040.KS": ("메리츠금융지주",  "KOSPI"),
    "005940.KS": ("NH투자증권",   "KOSPI"), "006800.KS": ("미래에셋증권",    "KOSPI"),
    "016360.KS": ("삼성증권",     "KOSPI"), "030000.KS": ("제일기획",        "KOSPI"),
    # KOSDAQ
    "086520.KQ": ("에코프로",     "KOSDAQ"), "247540.KQ": ("에코프로비엠",   "KOSDAQ"),
    "041510.KQ": ("SM",           "KOSDAQ"), "035900.KQ": ("JYP Ent.",       "KOSDAQ"),
    "122870.KQ": ("와이지엔터",   "KOSDAQ"), "263750.KQ": ("펄어비스",       "KOSDAQ"),
    "112040.KQ": ("위메이드",     "KOSDAQ"), "357780.KQ": ("솔브레인",       "KOSDAQ"),
    "066970.KQ": ("L&F",          "KOSDAQ"), "196170.KQ": ("알테오젠",       "KOSDAQ"),
    "039030.KQ": ("이오테크닉스", "KOSDAQ"), "078340.KQ": ("컴투스",         "KOSDAQ"),
    "950130.KQ": ("엑스페릭스",   "KOSDAQ"), "403870.KQ": ("HPSP",           "KOSDAQ"),
    "036540.KQ": ("SFA반도체",    "KOSDAQ"), "000250.KQ": ("삼천당제약",     "KOSDAQ"),
    "054040.KQ": ("한국컴퓨터",   "KOSDAQ"), "058470.KQ": ("리노공업",       "KOSDAQ"),
    "237690.KQ": ("에스티팜",     "KOSDAQ"), "214150.KQ": ("클래시스",       "KOSDAQ"),
    "039200.KQ": ("오스코텍",     "KOSDAQ"), "145020.KQ": ("휴젤",           "KOSDAQ"),
    "031860.KQ": ("엔씨엔",       "KOSDAQ"), "067160.KQ": ("아프리카TV",     "KOSDAQ"),
    "060310.KQ": ("3S",           "KOSDAQ"), "101490.KQ": ("에스앤에스텍",   "KOSDAQ"),
    "028300.KQ": ("HLB",          "KOSDAQ"), "091990.KQ": ("셀트리온헬스케어","KOSDAQ"),
    "108380.KQ": ("이노에너지",   "KOSDAQ"), "950160.KQ": ("코오롱티슈진",   "KOSDAQ"),
    "064760.KQ": ("티씨케이",     "KOSDAQ"), "240810.KQ": ("원익IPS",        "KOSDAQ"),
    "036930.KQ": ("주성엔지니어링","KOSDAQ"), "131970.KQ": ("두산테스나",     "KOSDAQ"),
    "058650.KQ": ("세경하이테크", "KOSDAQ"), "285130.KQ": ("SK바이오팜",     "KOSDAQ"),
    "178930.KQ": ("에이프로",     "KOSDAQ"), "336570.KQ": ("원익머트리얼즈", "KOSDAQ"),
    "131290.KQ": ("코스모로보틱스","KOSDAQ"), "064290.KQ": ("인텍플러스",     "KOSDAQ"),
    "140860.KQ": ("파크시스템스", "KOSDAQ"), "039290.KQ": ("태경케미컬",     "KOSDAQ"),
}


def get_domestic_top(n: int = 30, min_vol_krw: float = 10_000_000_000) -> pd.DataFrame:
    """yfinance로 주요 KOSPI + KOSDAQ 종목 시세 조회 후 거래대금·상승률 필터."""
    import yfinance as yf

    log.info("국내 시세 수집 중 (yfinance)...")
    tickers = list(_KR_TICKERS.keys())

    try:
        raw = yf.download(
            tickers,
            period="2d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        log.error("yfinance 국내 다운로드 실패: %s", e)
        return pd.DataFrame()

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close  = raw["Close"]
            volume = raw["Volume"]
        else:
            close  = raw[["Close"]]
            volume = raw[["Volume"]]
    except KeyError:
        close  = raw.xs("Close",  axis=1, level=0)
        volume = raw.xs("Volume", axis=1, level=0)

    if len(close) < 2:
        log.error("국내: 시세 행 부족 (%d행)", len(close))
        return pd.DataFrame()

    pct        = close.pct_change().iloc[-1] * 100
    last_close = close.iloc[-1]
    last_vol   = volume.iloc[-1]
    vol_krw    = last_close * last_vol  # 주가(KRW) × 거래량 = 거래대금

    rows = []
    for t in tickers:
        if t not in pct.index:
            continue
        name, market = _KR_TICKERS[t]
        rows.append({
            "티커":    t,
            "종목명":  name,
            "시장":    market,
            "등락률":  pct.get(t, float("nan")),
            "종가":    last_close.get(t, float("nan")),
            "거래대금": vol_krw.get(t, 0.0),
        })

    if not rows:
        log.error("국내 데이터 수집 실패")
        return pd.DataFrame()

    df = pd.DataFrame(rows).dropna(subset=["등락률", "종가"])
    df = df[df["거래대금"] >= min_vol_krw]
    df = df[df["등락률"] > 0]
    df = df.sort_values("등락률", ascending=False).head(n).reset_index(drop=True)
    df["순위"] = df.index + 1
    log.info("국내 상위 %d개 추출 완료", len(all_df))
    return all_df


def _fetch_sp500_tickers() -> set:
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=headers, timeout=15
        )
        dfs = pd.read_html(StringIO(r.text))
        tickers = set(dfs[0]["Symbol"].str.replace(".", "-", regex=False).tolist())
        if len(tickers) > 400:
            log.info("S&P500 %d개 (wikipedia)", len(tickers))
            return tickers
    except Exception as e:
        log.warning("S&P500 wikipedia 실패: %s", e)

    try:
        r = requests.get("https://slickcharts.com/sp500", headers=headers, timeout=15)
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            cols_l = [str(c).lower() for c in df.columns]
            sym = next((df.columns[i] for i, c in enumerate(cols_l)
                        if "symbol" in c or "ticker" in c), None)
            if sym:
                tickers = set(df[sym].dropna().astype(str)
                              .str.replace(".", "-", regex=False).tolist())
                if len(tickers) > 400:
                    log.info("S&P500 %d개 (slickcharts)", len(tickers))
                    return tickers
    except Exception as e:
        log.warning("S&P500 slickcharts 실패: %s", e)

    log.warning("S&P500 자동 수집 실패 → fallback 50개")
    return {
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK-B","LLY","JPM",
        "AVGO","TSLA","UNH","V","XOM","MA","JNJ","PG","HD","COST","MRK","ABBV",
        "CVX","KO","PEP","BAC","WMT","ORCL","ACN","TMO","MCD","CRM","CSCO","ABT",
        "NKE","DHR","TXN","PM","NEE","UPS","RTX","BMY","INTC","QCOM","AMT","LIN",
        "AMGN","SPGI","LOW","HON",
    }


def _fetch_nasdaq100_tickers() -> set:
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100",
                         headers=headers, timeout=15)
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            cols_l = [str(c).lower() for c in df.columns]
            sym = next((df.columns[i] for i, c in enumerate(cols_l)
                        if "ticker" in c or "symbol" in c), None)
            if sym:
                tickers = set(df[sym].dropna().astype(str).tolist())
                if len(tickers) > 80:
                    log.info("NASDAQ100 %d개 (wikipedia)", len(tickers))
                    return tickers
    except Exception as e:
        log.warning("NASDAQ100 wikipedia 실패: %s", e)

    try:
        r = requests.get("https://slickcharts.com/nasdaq100",
                         headers=headers, timeout=15)
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            cols_l = [str(c).lower() for c in df.columns]
            sym = next((df.columns[i] for i, c in enumerate(cols_l)
                        if "symbol" in c or "ticker" in c), None)
            if sym:
                tickers = set(df[sym].dropna().astype(str)
                              .str.replace(".", "-", regex=False).tolist())
                if len(tickers) > 80:
                    log.info("NASDAQ100 %d개 (slickcharts)", len(tickers))
                    return tickers
    except Exception as e:
        log.warning("NASDAQ100 slickcharts 실패: %s", e)

    log.warning("NASDAQ100 자동 수집 실패 → fallback 30개")
    return {
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","AVGO","TSLA","COST",
        "NFLX","TMUS","AMD","INTC","QCOM","CSCO","AMAT","MU","LRCX","ADI",
        "MRVL","KLAC","CDNS","SNPS","PYPL","ADBE","TXN","PANW","CRWD","ORLY",
    }


def get_foreign_top(n: int = 30, min_vol_usd: float = 50_000_000) -> pd.DataFrame:
    """S&P500 + NASDAQ 100 에서 거래대금 필터 후 상승률 상위 n개 반환"""
    import yfinance as yf

    sp500_tickers = _fetch_sp500_tickers()
    ndx_tickers   = _fetch_nasdaq100_tickers()
    all_tickers   = list(sp500_tickers | ndx_tickers)

    if not all_tickers:
        log.error("해외 티커 없음")
        return pd.DataFrame()

    log.info("해외 %d개 티커 시세 다운로드 중...", len(all_tickers))
    try:
        raw = yf.download(
            all_tickers,
            period="2d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        log.error("yfinance 다운로드 실패: %s", e)
        return pd.DataFrame()

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close  = raw["Close"]
            volume = raw["Volume"]
        else:
            close  = raw[["Close"]]
            volume = raw[["Volume"]]
    except KeyError:
        close  = raw.xs("Close",  axis=1, level=0)
        volume = raw.xs("Volume", axis=1, level=0)

    pct          = close.pct_change().iloc[-1] * 100
    last_close   = close.iloc[-1]
    last_vol     = volume.iloc[-1]
    last_usd_vol = last_close * last_vol

    df = pd.DataFrame({
        "티커":       pct.index.tolist(),
        "등락률":     pct.values,
        "종가":       last_close.values,
        "거래대금_USD": last_usd_vol.values,
    }).dropna()

    df["시장"] = df["티커"].apply(lambda t: "NASDAQ" if t in ndx_tickers else "S&P500")
    df = df[df["거래대금_USD"] >= min_vol_usd]
    df = df[df["등락률"] > 0]
    df = df.sort_values("등락률", ascending=False).head(n).reset_index(drop=True)
    df["순위"] = df.index + 1
    log.info("해외 상위 %d개 추출 완료", len(df))
    return df


# ═══════════════════════════════════════════════════════════
# 2단계: 뉴스 수집
# ═══════════════════════════════════════════════════════════

def fetch_domestic_news(ticker: str, name: str, count: int = 3) -> list:
    """Google News RSS로 국내 종목 뉴스 수집 (KST 오늘자)"""
    from xml.etree import ElementTree as ET
    from email.utils import parsedate_to_datetime

    today_kst = datetime.now(KST).date()
    query = quote(f"{name} 주가")
    url = (
        f"https://news.google.com/rss/search"
        f"?q={query}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")
        news  = []
        for item in items[:count * 3]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link",  "").strip()
            pub   = item.findtext("pubDate", "").strip()
            try:
                pub_date = parsedate_to_datetime(pub).astimezone(KST).date()
                if pub_date != today_kst:
                    continue
            except Exception:
                pass
            news.append({"title": title, "url": link})
            if len(news) >= count:
                break
        return news
    except Exception as e:
        log.warning("국내 뉴스 실패 [%s]: %s", name, e)
        return []


def _translate_ko(text: str) -> str:
    """Google Translate 비공식 API (영→한)"""
    if not text:
        return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text


def fetch_foreign_news(ticker: str, count: int = 3) -> list:
    """yfinance .news + 한글 번역"""
    import yfinance as yf

    today_kst = datetime.now(KST).date()
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception as e:
        log.warning("해외 뉴스 실패 [%s]: %s", ticker, e)
        return []

    result = []
    for item in raw_news[:count * 3]:
        content = item.get("content", {})
        title   = content.get("title", "") or item.get("title", "")
        url     = (content.get("canonicalUrl", {}).get("url", "")
                   or item.get("link", ""))
        pub_ts  = content.get("pubDate", "") or item.get("providerPublishTime", 0)

        try:
            if isinstance(pub_ts, (int, float)):
                pub_date = datetime.fromtimestamp(pub_ts, tz=KST).date()
            else:
                pub_date = datetime.fromisoformat(pub_ts).astimezone(KST).date()
            if pub_date != today_kst:
                continue
        except Exception:
            pass

        kor_title = _translate_ko(title)
        result.append({"title": kor_title, "title_en": title, "url": url})
        if len(result) >= count:
            break
    return result


# ═══════════════════════════════════════════════════════════
# 2.5단계: Groq AI 시황 요약
# ═══════════════════════════════════════════════════════════

def summarize_with_groq(dom_df: pd.DataFrame, for_df: pd.DataFrame,
                        dom_news: dict, for_news: dict) -> str:
    """Groq LLM으로 오늘 시황 한줄 요약 (GROQ_API_KEY 없으면 빈 문자열 반환)"""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        log.info("GROQ_API_KEY 없음 — AI 요약 건너뜀")
        return ""

    # 뉴스 헤드라인 수집 (국내 5 + 해외 3)
    headlines = []
    for _, r in dom_df.head(5).iterrows():
        nl = dom_news.get(r["티커"], [])
        tag = nl[0]["title"][:40] if nl else "뉴스 없음"
        headlines.append(f"[국내] {r['종목명']} (+{r['등락률']:.1f}%): {tag}")
    for _, r in for_df.head(3).iterrows():
        nl = for_news.get(r["티커"], [])
        tag = nl[0]["title"][:40] if nl else "No news"
        headlines.append(f"[해외] {r['티커']} (+{r['등락률']:.1f}%): {tag}")

    if not headlines:
        return ""

    prompt = (
        "다음은 오늘 강세 종목과 관련 뉴스입니다:\n"
        + "\n".join(headlines)
        + "\n\n위 정보를 바탕으로 오늘 주식 시장의 핵심 테마를 한 문장(30자 이내)으로 요약해주세요. "
        "예시: '반도체·방산 테마 강세, AI 인프라 수혜주 집중'\n"
        "한 문장만 출력하세요. 설명 없이."
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.3,
        )
        summary = resp.choices[0].message.content.strip()
        log.info("Groq 요약: %s", summary)
        return summary
    except Exception as e:
        log.warning("Groq 요약 실패: %s", e)
        return ""


# ═══════════════════════════════════════════════════════════
# 3단계: 마크다운 파일 생성
# ═══════════════════════════════════════════════════════════

def build_markdown(dom_df, for_df, dom_news, for_news, today: str) -> str:
    lines = [f"# 📈 강세 종목 브리핑 — {today}\n",
             "> 거래대금 필터: 국내 100억↑ / 해외 5천만달러↑\n"]

    lines.append("## 🏆 국내 TOP 30\n")
    lines.append("| 순위 | 종목명 | 코드 | 시장 | 등락률 | 종가 | 거래대금 |")
    lines.append("|:---:|---|---|:---:|:---:|---:|---:|")
    for _, r in dom_df.iterrows():
        vol_str = f"{r['거래대금'] / 1e8:.0f}억"
        lines.append(
            f"| {int(r['순위'])} | {r['종목명']} | {r['티커']} | {r['시장']} "
            f"| **+{r['등락률']:.2f}%** | {int(r['종가']):,}원 | {vol_str} |"
        )
    lines.append("")

    lines.append("## 🌐 해외 TOP 30\n")
    lines.append("| 순위 | 티커 | 시장 | 등락률 | 종가 | 거래대금 |")
    lines.append("|:---:|---|:---:|:---:|---:|---:|")
    for _, r in for_df.iterrows():
        vol_str = f"${r['거래대금_USD'] / 1e6:.0f}M"
        lines.append(
            f"| {int(r['순위'])} | {r['티커']} | {r['시장']} "
            f"| **+{r['등락률']:.2f}%** | ${r['종가']:.2f} | {vol_str} |"
        )
    lines.append("")

    lines.append("## 📰 종목별 뉴스 (TOP 10)\n")
    for _, r in dom_df.head(10).iterrows():
        nl = dom_news.get(r["티커"], [])
        lines.append(f"### {r['종목명']} ({r['티커']}) +{r['등락률']:.2f}%")
        lines.extend([f"- [{n['title']}]({n['url']})" for n in nl] or ["- 오늘자 뉴스 없음"])
        lines.append("")
    for _, r in for_df.head(10).iterrows():
        nl = for_news.get(r["티커"], [])
        lines.append(f"### {r['티커']} ({r['시장']}) +{r['등락률']:.2f}%")
        if nl:
            for n in nl:
                lines.append(f"- {n['title']}\n  _{n.get('title_en','')}_\n  {n['url']}")
        else:
            lines.append("- 오늘자 뉴스 없음")
        lines.append("")

    top_dom = ", ".join(dom_df.head(3)["종목명"].tolist()) if not dom_df.empty else "-"
    top_for = ", ".join(for_df.head(3)["티커"].tolist())  if not for_df.empty else "-"
    lines += [
        "## 💡 오늘의 핵심 한 줄\n",
        f"국내 강세: **{top_dom}** / 해외 강세: **{top_for}**\n",
        "## 📌 오늘의 주목 액션\n",
    ]
    for i, (_, r) in enumerate(dom_df.head(3).iterrows(), 1):
        nl = dom_news.get(r["티커"], [])
        reason = nl[0]["title"] if nl else "뉴스 확인 필요"
        lines.append(f"{i}. **{r['종목명']} ({r['티커']})** — {reason}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 4단계: 텔레그램 발송
# ═══════════════════════════════════════════════════════════

def _split_msg(text: str, limit: int = 4096) -> list:
    if len(text) <= limit:
        return [text]
    chunks, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > limit:
            chunks.append(buf)
            buf = ""
        buf += line
    if buf:
        chunks.append(buf)
    return chunks


def send_telegram(message: str, max_retry: int = 3) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수 미설정")
        return False

    url    = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = _split_msg(message)

    for i, chunk in enumerate(chunks, 1):
        payload = {"chat_id": chat_id, "text": chunk,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        for attempt in range(1, max_retry + 1):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                resp.raise_for_status()
                log.info("텔레그램 발송 성공 (청크 %d/%d)", i, len(chunks))
                time.sleep(0.5)
                break
            except Exception as e:
                log.warning("텔레그램 재시도 %d/%d: %s", attempt, max_retry, e)
                if attempt == max_retry:
                    log.error("텔레그램 최종 실패 청크 %d", i)
                    return False
                time.sleep(2)
    return True


def build_telegram_message(dom_df, for_df, dom_news, for_news,
                           today: str, groq_summary: str = "") -> str:
    lines = [
        f"<b>📈 오늘의 강세주★ (KOSPI/KOSDAQ)</b>",
        f"{today} 장마감 기준 · 거래대금 100억↑",
    ]

    # Groq AI 요약 (있을 때만 표시)
    if groq_summary:
        lines += ["─" * 28, f"🤖 <b>AI 시황:</b> {groq_summary}"]

    lines += ["─" * 28, "", "<b>🏆 국내 TOP 3</b>", ""]

    for _, r in dom_df.head(3).iterrows():
        nl = dom_news.get(r["티커"], [])
        issue  = nl[0]["title"][:25] if nl else "이슈 확인 필요"
        detail = nl[1]["title"][:55] if len(nl) > 1 else (nl[0]["title"][:55] if nl else "")
        lines += [
            f"▶ <b>{r['종목명']} ({r['티커']})</b> +{r['등락률']:.2f}%",
            issue,
            f"▷ {detail}" if detail else "",
            "",
        ]

    lines += ["─" * 28, "", "<b>🌐 해외 TOP 3</b>", ""]

    for _, r in for_df.head(3).iterrows():
        nl = for_news.get(r["티커"], [])
        issue  = nl[0]["title"][:25] if nl else "이슈 확인 필요"
        detail = nl[1]["title"][:55] if len(nl) > 1 else (nl[0]["title"][:55] if nl else "")
        lines += [
            f"▶ <b>{r['티커']} ({r['시장']})</b> +{r['등락률']:.2f}%",
            issue,
            f"▷ {detail}" if detail else "",
            "",
        ]

    lines.append("─" * 28)
    top_dom = " · ".join(dom_df.head(3)["종목명"].tolist()) if not dom_df.empty else "-"
    top_for = " · ".join(for_df.head(3)["티커"].tolist())  if not for_df.empty else "-"
    lines.append(f"💡 <b>오늘의 테마:</b> {top_dom} / {top_for}")

    if not dom_df.empty:
        r0 = dom_df.iloc[0]
        n0 = dom_news.get(r0["티커"], [])
        action = n0[0]["title"][:35] if n0 else "뉴스 확인"
        lines.append(f"📌 <b>주목 액션:</b> {r0['종목명']} — {action}")

    lines.append("─" * 28)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════

def run_briefing():
    now_kst = datetime.now(KST)
    today   = now_kst.strftime("%Y-%m-%d")
    log.info("=" * 50)
    log.info("브리핑 시작: %s", now_kst.strftime("%Y-%m-%d %H:%M KST"))

    # 1단계
    dom_df = get_domestic_top()
    for_df = get_foreign_top()

    if dom_df.empty and for_df.empty:
        log.error("스크리닝 결과 없음 — 종료")
        return

    # 2단계
    log.info("국내 뉴스 수집 중...")
    dom_news = {}
    for _, r in dom_df.iterrows():
        dom_news[r["티커"]] = fetch_domestic_news(r["티커"], r["종목명"])
        time.sleep(0.3)

    log.info("해외 뉴스 수집 중...")
    for_news = {}
    for _, r in for_df.iterrows():
        for_news[r["티커"]] = fetch_foreign_news(r["티커"])
        time.sleep(0.2)

    # 2.5단계: Groq AI 요약
    groq_summary = summarize_with_groq(dom_df, for_df, dom_news, for_news)

    # 3단계
    md = build_markdown(dom_df, for_df, dom_news, for_news, today)
    out_dir = Path("briefings")
    out_dir.mkdir(exist_ok=True)
    md_path = out_dir / f"{now_kst.strftime('%Y%m%d')}_강세종목브리핑.md"
    md_path.write_text(md, encoding="utf-8")
    log.info("마크다운 저장: %s", md_path)

    # 4단계
    msg = build_telegram_message(dom_df, for_df, dom_news, for_news,
                                  today, groq_summary=groq_summary)
    ok  = send_telegram(msg)
    log.info("텔레그램 발송 %s", "완료 ✅" if ok else "실패 ❌")
    log.info("=" * 50)


# ═══════════════════════════════════════════════════════════
# 5단계: 스케줄러 (로컬 실행 전용 — GitHub Actions에선 사용 안 함)
# ═══════════════════════════════════════════════════════════

def start_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        run_briefing,
        trigger="cron",
        day_of_week="mon-fri",
        hour=16,
        minute=30,
        id="daily_briefing",
        replace_existing=True,
    )
    log.info("스케줄 등록 완료 — 매일 16:30 KST (평일)")
    log.info("Ctrl+C 로 중단")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("스케줄러 종료")


# ═══════════════════════════════════════════════════════════
# 진입점
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "schedule"

    if mode == "now":
        run_briefing()
    elif mode == "schedule":
        start_scheduler()
    else:
        print("사용법:")
        print("  python briefing.py now       # 즉시 실행 (테스트)")
        print("  python briefing.py schedule  # 매일 16:30 자동 실행 (로컬)")
