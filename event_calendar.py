# -*- coding: utf-8 -*-
"""이벤트 캘린더 — 어닝 D-day, FOMC/CPI 등 발표일 조회."""
from __future__ import annotations
import datetime as dt
from typing import Optional, Tuple, Dict


def earnings_dday(ticker: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Returns:
        (dday, iso_date_str) — dday 양수=미래, 음수=과거, None=정보없음
    네트워크/모듈 실패 시 (None, None) 안전 폴백.
    """
    try:
        import yfinance as yf
    except Exception:
        return (None, None)

    try:
        tk = yf.Ticker(ticker)
        # 1) calendar (단일 다음 어닝)
        cal = getattr(tk, "calendar", None)
        target = None
        if cal is not None:
            try:
                if hasattr(cal, "loc"):     # DataFrame 형식
                    if "Earnings Date" in cal.index:
                        v = cal.loc["Earnings Date"]
                        target = v.iloc[0] if hasattr(v, "iloc") else v
                elif isinstance(cal, dict):
                    val = cal.get("Earnings Date")
                    if isinstance(val, list) and val:
                        target = val[0]
                    else:
                        target = val
            except Exception:
                target = None

        # 2) earnings_dates (DataFrame, 인덱스가 datetime)
        if target is None:
            try:
                ed = tk.earnings_dates
                if ed is not None and len(ed) > 0:
                    today = dt.datetime.now(dt.timezone.utc).date()
                    future = [i for i in ed.index
                              if hasattr(i, "date") and i.date() >= today]
                    if future:
                        target = future[0]
                    else:
                        target = ed.index[0]
            except Exception:
                pass

        if target is None:
            return (None, None)

        d = target.date() if hasattr(target, "date") else target
        if isinstance(d, str):
            d = dt.date.fromisoformat(d[:10])
        today = dt.date.today()
        dday = (d - today).days
        return (dday, d.isoformat())
    except Exception:
        return (None, None)


def build_dday_chip(dday: Optional[int]) -> Dict[str, str]:
    """D-day 칩 표시용 색·문자열."""
    if dday is None:
        return {"text": "", "fg": "#888", "bg": "#EEEEEE", "show": False}
    if dday < 0:
        return {"text": f"어닝 D+{-dday}", "fg": "#FFF", "bg": "#888888", "show": True}
    if dday == 0:
        return {"text": "어닝 D-DAY", "fg": "#FFF", "bg": "#F04452", "show": True}
    if dday <= 3:
        return {"text": f"어닝 D-{dday}", "fg": "#FFF", "bg": "#F04452", "show": True}
    if dday <= 7:
        return {"text": f"어닝 D-{dday}", "fg": "#191919", "bg": "#FFD43A", "show": True}
    if dday <= 30:
        return {"text": f"어닝 D-{dday}", "fg": "#444", "bg": "#EAF2FF", "show": True}
    return {"text": "", "fg": "#888", "bg": "#EEEEEE", "show": False}


if __name__ == "__main__":
    chip0 = build_dday_chip(0)
    chip3 = build_dday_chip(3)
    chip10 = build_dday_chip(10)
    chipN = build_dday_chip(None)
    assert chip0["show"] and chip0["bg"] == "#F04452"
    assert chip3["show"]
    assert chip10["show"] and chip10["bg"] == "#EAF2FF"
    assert not chipN["show"]
    print("[OK] event_calendar chips")

    # 라이브 호출은 네트워크 의존 — 예외 없이만 통과
    d, s = earnings_dday("AAPL")
    print(f"AAPL earnings: dday={d}, date={s}")
