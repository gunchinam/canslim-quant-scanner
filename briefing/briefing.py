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

def get_domestic_top(n: int = 30, min_vol_krw: float = 10_000_000_000) -> pd.DataFrame:
    """pykrx로 KOSPI + KOSDAQ 전종목 조회 후 거래대금·상승률 필터."""
    from pykrx import stock

    date_str = _trading_date()
    log.info("국내 시세 수집 중 (%s)...", date_str)

    rows = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            if df is None or df.empty:
                log.warning("%s: 빈 응답", market)
                continue

            rename = {}
            for col in df.columns:
                c = str(col)
                if "종가" in c:
                    rename[col] = "종가"
                elif "등락" in c:
                    rename[col] = "등락률"
                elif "거래대금" in c:
                    rename[col] = "거래대금"
            df = df.rename(columns=rename)

            missing = [c for c in ["종가", "등락률", "거래대금"] if c not in df.columns]
            if missing:
                log.warning("%s: 컬럼 누락 %s", market, missing)
                continue

            df = df[["종가", "등락률", "거래대금"]].copy()
            df["시장"] = market
            df.index.name = "티커"
            df.reset_index(inplace=True)

            names = {t: stock.get_market_ticker_name(t) for t in df["티커"]}
            df["종목명"] = df["티커"].map(names)
            rows.append(df)
            log.info("%s: %d개 종목 수집", market, len(df))

        except Exception as e:
            log.warning("%s 수집 실패: %s", market, e)

    if not rows:
        log.error("국내 데이터 수집 실패")
        return pd.DataFrame()

    all_df = pd.concat(rows, ignore_index=True)
    all_df = all_df[all_df["거래대금"] >= min_vol_krw]
    all_df = all_df[all_df["등락률"] > 0]
    all_df = all_df.sort_values("등락률", ascending=False).head(n).reset_index(drop=True)
    all_df["순위"] = all_df.index + 1
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
