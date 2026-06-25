import logging
import yfinance as yf
from tradingkey_api import is_kr_ticker, get_tradingkey_data

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


def _get_market_cap(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).info.get("marketCap", 0))
    except Exception:
        return 0.0


def _get_ebit(ticker: str) -> float:
    try:
        t = yf.Ticker(ticker)
        ebit = t.income_stmt.loc["EBIT"].iloc[0]
        return float(ebit)
    except Exception:
        try:
            t = yf.Ticker(ticker)
            inc = t.income_stmt
            op_income = float(inc.loc["Operating Income"].iloc[0])
            return op_income
        except Exception:
            return 0.0


def _get_retained_earnings(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).balance_sheet.loc["Retained Earnings"].iloc[0])
    except Exception:
        return 0.0


def _get_ppe(ticker: str) -> tuple[float, float]:
    try:
        bs = yf.Ticker(ticker).balance_sheet
        curr = float(bs.loc["Net PPE"].iloc[0])
        prev = float(bs.loc["Net PPE"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def _get_depreciation(ticker: str) -> float:
    try:
        return float(yf.Ticker(ticker).cashflow.loc["Depreciation And Amortization"].iloc[0])
    except Exception:
        return 0.0


def _get_long_term_assets(ticker: str) -> tuple[float, float]:
    try:
        bs = yf.Ticker(ticker).balance_sheet
        curr = float(bs.loc["Other Non Current Assets"].iloc[0])
        prev = float(bs.loc["Other Non Current Assets"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def _get_sga(ticker: str) -> tuple[float, float]:
    try:
        inc = yf.Ticker(ticker).income_stmt
        curr = float(inc.loc["Selling General And Administration"].iloc[0])
        prev = float(inc.loc["Selling General And Administration"].iloc[1])
        return curr, prev
    except Exception:
        return 0.0, 0.0


def calculate_altman_z(ticker: str) -> float | None:
    """Altman Z-Score. >2.99=안전, 1.81~2.99=회색, <1.81=위험."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, _ = _get_financials(ticker)
        ta = curr["Total Assets"]
        if ta == 0:
            return None

        working_capital = curr["Current Assets"] - curr["Current Liabilities"]
        retained_earnings = _get_retained_earnings(ticker)
        ebit = _get_ebit(ticker)
        market_cap = _get_market_cap(ticker)
        total_liabilities = curr["Long Term Debt"] + curr["Current Liabilities"]
        revenue = curr["Total Revenue"]

        x1 = working_capital / ta
        x2 = retained_earnings / ta
        x3 = ebit / ta
        x4 = market_cap / total_liabilities if total_liabilities else 0
        x5 = revenue / ta

        z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        return round(float(z), 3)
    except Exception as e:
        logger.warning(f"Altman Z failed for {ticker}: {e}")
        return None


def calculate_beneish_m(ticker: str) -> tuple[float, bool] | None:
    """Beneish M-Score. > -1.78: 분식 의심 경고."""
    if is_kr_ticker(ticker):
        return None
    try:
        curr, prev = _get_financials(ticker)
        ta_curr = curr["Total Assets"]
        ta_prev = prev["Total Assets"]
        if ta_curr == 0 or ta_prev == 0:
            return None

        rev_curr = curr["Total Revenue"]
        rev_prev = prev["Total Revenue"]
        gp_curr = curr["Gross Profit"]
        gp_prev = prev["Gross Profit"]
        ppe_curr, ppe_prev = _get_ppe(ticker)
        depr = _get_depreciation(ticker)
        lt_curr, lt_prev = _get_long_term_assets(ticker)
        sga_curr, sga_prev = _get_sga(ticker)

        # DSRI: Days Sales Receivable Index
        rec_curr = curr["Current Assets"] * 0.3  # 근사값
        rec_prev = prev["Current Assets"] * 0.3
        dsri = (rec_curr / rev_curr) / (rec_prev / rev_prev) if rev_prev and rev_curr else 1

        # GMI: Gross Margin Index
        gm_prev = gp_prev / rev_prev if rev_prev else 0
        gm_curr = gp_curr / rev_curr if rev_curr else 0
        gmi = gm_prev / gm_curr if gm_curr else 1

        # AQI: Asset Quality Index
        aqi_curr = (ta_curr - curr["Current Assets"] - ppe_curr) / ta_curr
        aqi_prev = (ta_prev - prev["Current Assets"] - ppe_prev) / ta_prev
        aqi = aqi_curr / aqi_prev if aqi_prev else 1

        # SGI: Sales Growth Index
        sgi = rev_curr / rev_prev if rev_prev else 1

        # DEPI: Depreciation Index
        dep_rate_prev = ppe_prev / (ppe_prev + depr) if (ppe_prev + depr) else 0.5
        dep_rate_curr = ppe_curr / (ppe_curr + depr) if (ppe_curr + depr) else 0.5
        depi = dep_rate_prev / dep_rate_curr if dep_rate_curr else 1

        # SGAI: SGA Expense Index
        sgai = (sga_curr / rev_curr) / (sga_prev / rev_prev) if sga_prev and rev_prev and rev_curr else 1

        # LVGI: Leverage Index
        lev_curr = curr["Long Term Debt"] / ta_curr
        lev_prev = prev["Long Term Debt"] / ta_prev
        lvgi = lev_curr / lev_prev if lev_prev else 1

        # TATA: Total Accruals to Total Assets
        tata = (curr["Net Income"] - curr["Operating Cash Flow"]) / ta_curr

        m = (-4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi
             + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi)

        return round(float(m), 3), m > -1.78
    except Exception as e:
        logger.warning(f"Beneish M failed for {ticker}: {e}")
        return None


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


def _calc_quantitative_score(tk_data: dict, piotroski: int) -> int:
    """100점 정량 스코어 계산.

    배점:
    - TradingKey overall 스코어 (80점): 종합 밸류에이션/성장/수익성 반영
    - Piotroski F-Score 정규화 (10점): 재무 건전성
    - QoQ 모멘텀 (10점): 기관 보유 QoQ + 1개월 주가 성과
    """
    tk_score = tk_data.get("score", {})
    inst = tk_data.get("institutional", {})
    perf = tk_data.get("performance", {})

    # TradingKey overall 스코어 → 80점 환산
    overall = tk_score.get("overall", 0)
    score = int(overall / 100 * 80)

    # Piotroski F-Score → 10점 환산 (9점 만점 정규화)
    pio_pts = int((piotroski / 9) * 10) if piotroski else 0
    score += pio_pts

    # QoQ 모멘텀 (10점)
    holding_qoq = inst.get("holding_qoq", 0)
    if holding_qoq > 5:
        score += 4
    elif holding_qoq > 0:
        score += 2

    rev_1m = perf.get("1m", 0)
    if rev_1m > 5:
        score += 6
    elif rev_1m > 0:
        score += 3
    elif rev_1m > -5:
        score += 1

    return min(100, max(0, score))


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 55:
        return "B"
    if score >= 35:
        return "C"
    return "D"


def _grade_to_rating(grade: str) -> str:
    mapping = {"A+": "Conviction Buy", "A": "Buy", "B": "Neutral", "C": "Reduce", "D": "Sell"}
    return mapping.get(grade, "Neutral")


def get_nomura_score(ticker: str) -> dict | None:
    """노무라式 종합 스코어 반환."""
    if is_kr_ticker(ticker):
        return None
    try:
        tk_data = get_tradingkey_data(ticker)  # None이어도 yfinance 지표로 계속 진행

        piotroski = calculate_piotroski(ticker) or 0
        altman_z = calculate_altman_z(ticker)
        beneish_result = calculate_beneish_m(ticker)
        beneish_m = beneish_result[0] if beneish_result else None
        beneish_warn = beneish_result[1] if beneish_result else False

        td = tk_data or {}
        q_score = _calc_quantitative_score(td, piotroski)
        grade = _score_to_grade(q_score)
        rating = _grade_to_rating(grade)

        analyst = td.get("analyst", {})
        target = analyst.get("target_price", 0.0)
        upside = analyst.get("upside_pct", 0.0)

        return {
            "quantitative_score": q_score,
            "grade": grade,
            "piotroski": piotroski,
            "altman_z": altman_z,
            "beneish_m": beneish_m,
            "beneish_warning": beneish_warn,
            "nomura_rating": rating,
            "nomura_target": float(target),
            "nomura_upside": float(upside),
        }
    except Exception as e:
        logger.warning(f"get_nomura_score failed for {ticker}: {e}")
        return None
