import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import nomura_score


# --- Piotroski ---

def _make_financials(net_income, total_assets, operating_cf,
                     long_term_debt, current_assets, current_liabilities,
                     shares, revenue, gross_profit,
                     prev_net_income=None, prev_total_assets=None,
                     prev_long_term_debt=None, prev_current_assets=None,
                     prev_current_liabilities=None, prev_shares=None,
                     prev_revenue=None, prev_gross_profit=None):
    """yfinance balance_sheet / income_stmt / cashflow 구조 모킹 헬퍼."""
    # 현재 연도
    curr = {
        "Net Income": net_income,
        "Total Assets": total_assets,
        "Operating Cash Flow": operating_cf,
        "Long Term Debt": long_term_debt,
        "Current Assets": current_assets,
        "Current Liabilities": current_liabilities,
        "Ordinary Shares Number": shares,
        "Total Revenue": revenue,
        "Gross Profit": gross_profit,
    }
    # 이전 연도 (기본값: 동일)
    prev = {
        "Net Income": prev_net_income or net_income,
        "Total Assets": prev_total_assets or total_assets,
        "Long Term Debt": prev_long_term_debt or long_term_debt,
        "Current Assets": prev_current_assets or current_assets,
        "Current Liabilities": prev_current_liabilities or current_liabilities,
        "Ordinary Shares Number": prev_shares or shares,
        "Total Revenue": prev_revenue or revenue,
        "Gross Profit": prev_gross_profit or gross_profit,
    }
    return curr, prev


def test_piotroski_perfect_score():
    """9/9 조건 충족 케이스."""
    curr, prev = _make_financials(
        net_income=1000, total_assets=5000, operating_cf=1200,
        long_term_debt=500, current_assets=2000, current_liabilities=800,
        shares=100, revenue=10000, gross_profit=4000,
        prev_net_income=800, prev_total_assets=4500,
        prev_long_term_debt=600, prev_current_assets=1500,
        prev_current_liabilities=700, prev_shares=105,
        prev_revenue=8900, prev_gross_profit=3400,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        score = nomura_score.calculate_piotroski("AAPL")
    assert score == 9


def test_piotroski_zero_score():
    """0/9 조건: 손실, 음수 CF, 부채증가 등."""
    curr, prev = _make_financials(
        net_income=-500, total_assets=5000, operating_cf=-600,
        long_term_debt=1000, current_assets=800, current_liabilities=900,
        shares=110, revenue=8000, gross_profit=2000,
        prev_net_income=800, prev_total_assets=4000,
        prev_long_term_debt=800, prev_current_assets=1500,
        prev_current_liabilities=700, prev_shares=100,
        prev_revenue=9000, prev_gross_profit=3200,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        score = nomura_score.calculate_piotroski("AAPL")
    assert score == 0


def test_piotroski_returns_int():
    curr, prev = _make_financials(
        net_income=100, total_assets=1000, operating_cf=150,
        long_term_debt=200, current_assets=500, current_liabilities=300,
        shares=50, revenue=2000, gross_profit=800,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)):
        result = nomura_score.calculate_piotroski("AAPL")
    assert isinstance(result, int)
    assert 0 <= result <= 9


def test_piotroski_kr_returns_none():
    result = nomura_score.calculate_piotroski("005930.KS")
    assert result is None


# --- Altman Z-Score ---

def test_altman_z_safe_zone():
    """Z > 2.99 = 안전."""
    curr, prev = _make_financials(
        net_income=2000, total_assets=10000, operating_cf=2500,
        long_term_debt=1000, current_assets=4000, current_liabilities=2000,
        shares=100, revenue=15000, gross_profit=7000,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_market_cap", return_value=25000.0), \
         patch("nomura_score._get_ebit", return_value=2500.0), \
         patch("nomura_score._get_retained_earnings", return_value=5000.0):
        z = nomura_score.calculate_altman_z("AAPL")
    assert z is not None
    assert z > 2.99


def test_altman_z_returns_float():
    curr, prev = _make_financials(
        net_income=100, total_assets=1000, operating_cf=150,
        long_term_debt=200, current_assets=500, current_liabilities=300,
        shares=50, revenue=2000, gross_profit=800,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_market_cap", return_value=2000.0), \
         patch("nomura_score._get_ebit", return_value=200.0), \
         patch("nomura_score._get_retained_earnings", return_value=300.0):
        z = nomura_score.calculate_altman_z("AAPL")
    assert isinstance(z, float)


# --- Beneish M-Score ---

def test_beneish_no_warning():
    """M < -1.78: 분식 없음."""
    curr, prev = _make_financials(
        net_income=1000, total_assets=5000, operating_cf=1200,
        long_term_debt=500, current_assets=2000, current_liabilities=800,
        shares=100, revenue=10000, gross_profit=4500,
        prev_net_income=900, prev_total_assets=4800,
        prev_revenue=9500, prev_gross_profit=4200,
    )
    with patch("nomura_score._get_financials", return_value=(curr, prev)), \
         patch("nomura_score._get_ppe", return_value=(1000.0, 950.0)), \
         patch("nomura_score._get_depreciation", return_value=200.0), \
         patch("nomura_score._get_long_term_assets", return_value=(500.0, 480.0)), \
         patch("nomura_score._get_sga", return_value=(500.0, 480.0)):
        m, warning = nomura_score.calculate_beneish_m("AAPL")
    assert isinstance(m, float)
    assert warning is False


def test_beneish_kr_returns_none():
    result = nomura_score.calculate_beneish_m("005930.KS")
    assert result is None
