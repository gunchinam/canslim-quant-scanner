import logging
import yfinance as yf
from tradingkey_api import is_kr_ticker

logger = logging.getLogger(__name__)


def _get_financials(ticker: str) -> tuple[dict, dict]:
    """yfinance에서 현재/이전 연도 재무 데이터 반환."""
    t = yf.Ticker(ticker)
    bs = t.balance_sheet
    inc = t.income_stmt
    cf = t.cashflow

    def _get(df, key, col=0, default=0.0):
        try:
            return float(df.loc[key].iloc[col])
        except Exception:
            return float(default)

    curr = {
        "Net Income": _get(inc, "Net Income"),
        "Total Assets": _get(bs, "Total Assets"),
        "Operating Cash Flow": _get(cf, "Operating Cash Flow"),
        "Long Term Debt": _get(bs, "Long Term Debt"),
        "Current Assets": _get(bs, "Current Assets"),
        "Current Liabilities": _get(bs, "Current Liabilities"),
        "Ordinary Shares Number": _get(bs, "Ordinary Shares Number"),
        "Total Revenue": _get(inc, "Total Revenue"),
        "Gross Profit": _get(inc, "Gross Profit"),
    }
    prev = {
        "Net Income": _get(inc, "Net Income", col=1),
        "Total Assets": _get(bs, "Total Assets", col=1),
        "Long Term Debt": _get(bs, "Long Term Debt", col=1),
        "Current Assets": _get(bs, "Current Assets", col=1),
        "Current Liabilities": _get(bs, "Current Liabilities", col=1),
        "Ordinary Shares Number": _get(bs, "Ordinary Shares Number", col=1),
        "Total Revenue": _get(inc, "Total Revenue", col=1),
        "Gross Profit": _get(inc, "Gross Profit", col=1),
    }
    return curr, prev


def calculate_piotroski(ticker: str) -> int | None:
    """Piotroski F-Score (0~9) 계산."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, prev = _get_financials(ticker)
        score = 0

        ta = curr["Total Assets"]
        prev_ta = prev["Total Assets"]
        if ta == 0:
            return 0

        # F1: ROA > 0
        roa = curr["Net Income"] / ta
        if roa > 0:
            score += 1

        # F2: Operating Cash Flow > 0
        if curr["Operating Cash Flow"] > 0:
            score += 1

        # F3: ROA 증가
        prev_roa = prev["Net Income"] / prev_ta if prev_ta else 0
        if roa > prev_roa:
            score += 1

        # F4: Accruals (CF/TA > ROA)
        if curr["Operating Cash Flow"] / ta > roa:
            score += 1

        # F5: 부채 비율 감소
        curr_lev = curr["Long Term Debt"] / ta
        prev_lev = prev["Long Term Debt"] / prev_ta if prev_ta else 0
        if curr_lev < prev_lev:
            score += 1

        # F6: 유동비율 증가
        curr_cr = curr["Current Assets"] / curr["Current Liabilities"] if curr["Current Liabilities"] else 0
        prev_cr = prev["Current Assets"] / prev["Current Liabilities"] if prev["Current Liabilities"] else 0
        if curr_cr > prev_cr:
            score += 1

        # F7: 신주 발행 없음 (주식수 감소 또는 동일)
        if curr["Ordinary Shares Number"] <= prev["Ordinary Shares Number"]:
            score += 1

        # F8: Gross Margin 개선
        curr_gm = curr["Gross Profit"] / curr["Total Revenue"] if curr["Total Revenue"] else 0
        prev_gm = prev["Gross Profit"] / prev["Total Revenue"] if prev["Total Revenue"] else 0
        if curr_gm > prev_gm:
            score += 1

        # F9: Asset Turnover 증가
        curr_at = curr["Total Revenue"] / ta
        prev_at = prev["Total Revenue"] / prev_ta if prev_ta else 0
        if curr_at > prev_at:
            score += 1

        return score
    except Exception as e:
        logger.warning(f"Piotroski calculation failed for {ticker}: {e}")
        return None
