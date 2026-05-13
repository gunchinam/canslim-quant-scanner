"""
app.py — (.)(.)검색기 Flask 웹 서버
engine_adapter.ScanAdapter를 JSON API로 서빙하고 HTML 템플릿을 렌더링한다.

실행: python web_app/app.py
접속: http://localhost:5000
"""
import sys
import os
import io
import base64
import logging

sys.path.insert(0, os.path.dirname(__file__))

# 프로젝트 루트 경로 (four_axis_analyzer, handdrawn_renderer 접근용)
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from flask import Flask, request, jsonify, render_template
from engine_adapter import ScanAdapter
from config_manager import (
    SETTINGS_SCHEMA, load_config, save_config,
    apply_to_environ, get_masked, get_connection_status,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# 앱 시작 시 저장된 설정을 환경변수에 반영
apply_to_environ()

# (섹터 히트/핫 섹터 기능 제거됨 — yfinance rate-limit 부담 ↓, UI 정리)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)


def _make_adapter() -> ScanAdapter:
    market   = request.args.get("market",   "US")
    strategy = request.args.get("strategy", "BALANCED")
    return ScanAdapter(market=market, strategy=strategy)


@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# ── 페이지 라우트 ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("scanner.html")


@app.route("/detail/<ticker>")
def detail(ticker: str):
    return render_template("detail.html", ticker=ticker)


@app.route("/settings")
def settings_page():
    return render_template("settings.html", schema=SETTINGS_SCHEMA)


# ── 설정 API ─────────────────────────────────────────────────────────

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """현재 저장된 설정 조회 (민감값 마스킹)."""
    data = load_config()
    return jsonify({
        "values": data,
        "values_masked": get_masked(data),
        "status": get_connection_status(data),
        "schema": SETTINGS_SCHEMA,
    })


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """설정 저장 후 환경변수에 즉시 반영."""
    try:
        incoming = request.get_json(force=True) or {}
        existing = load_config()
        # 새 값만 업데이트 (빈 값은 기존 유지)
        for key, value in incoming.items():
            if value is not None and value != "":
                existing[key] = value
        save_config(existing)
        apply_to_environ(existing)
        return jsonify({"ok": True})
    except Exception as e:
        logging.exception("api_settings_post")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/settings", methods=["DELETE"])
def api_settings_delete():
    """설정 초기화."""
    try:
        save_config({})
        return jsonify({"ok": True})
    except Exception as e:
        logging.exception("api_settings_delete")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── JSON API ─────────────────────────────────────────────────────────────

@app.route("/api/sectors")
def api_sectors():
    """GET /api/sectors?market=US → {"sectors": {섹터명: [ticker, ...]}}"""
    try:
        adapter = _make_adapter()
        return jsonify({
            "sectors": adapter.get_sectors(),
            "groups":  adapter.get_sector_groups(),
        })
    except Exception as e:
        logging.exception("api_sectors")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan")
def api_scan():
    """GET /api/scan?market=US&strategy=BALANCED&sector=SaaS → [{...}, ...]"""
    try:
        adapter = _make_adapter()
        sector  = request.args.get("sector", "")
        market  = (request.args.get("market") or "US").upper()
        results = adapter.scan_sector(sector) if sector else adapter.scan_all()
        # 어제 대비 점수/순위 변동 주석
        try:
            import history
            results = history.annotate_deltas(results, market)
            # 전체 스캔일 때만 스냅샷 갱신 (섹터 부분 스캔은 기준 오염 방지)
            if not sector:
                history.save_snapshot(results, market)
        except Exception as he:
            logging.warning("history annotate/save failed: %s", he)
        return jsonify(results)
    except Exception as e:
        logging.exception("api_scan")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ticker/<ticker>")
def api_ticker(ticker: str):
    """GET /api/ticker/AAPL?market=US&strategy=BALANCED → {Ticker, TotalScore, ...}"""
    try:
        adapter = _make_adapter()
        result  = adapter.analyze_ticker(ticker)
        if result is None:
            return jsonify({"error": "분석 실패 또는 데이터 없음"}), 404
        return jsonify(result)
    except Exception as e:
        logging.exception("api_ticker")
        return jsonify({"error": str(e)}), 500


@app.route("/api/four_axis/<ticker>")
def api_four_axis(ticker: str):
    """4축 핸드드로윙 차트 + 분석 데이터 반환 (base64 PNG)."""
    try:
        import yfinance as yf
        from four_axis_analyzer import FourAxisAnalyzer
        from handdrawn_renderer import HandDrawnChartRenderer

        market = request.args.get("market", "US")

        # 시도할 ticker 후보 리스트 — 마켓별로 변형을 모두 시도
        if market == "US":
            candidates = [ticker, ticker.upper()]
        else:
            # KR: 기존 .KS/.KQ 접미사 제거 후 6자리 패딩
            base = ticker
            for suf in (".KS", ".KQ", ".ks", ".kq"):
                if base.endswith(suf):
                    base = base[: -len(suf)]
                    break
            t6 = base.zfill(6) if base.isdigit() else base
            candidates = [f"{t6}.KS", f"{t6}.KQ", f"{base}.KS", f"{base}.KQ"]

        # 중복 제거 (순서 유지)
        seen_yt = set()
        candidates = [c for c in candidates if not (c in seen_yt or seen_yt.add(c))]

        # 다중 기간 폴백 — 2y → 1y → 6mo → 3mo 순으로 시도
        # 일부 ETF/저유동 종목은 1y로는 비어있고 6mo 이하에서만 데이터가 나오기도 함
        hist = None
        tried = []
        periods = ("2y", "1y", "6mo", "3mo")
        min_rows = 20  # 30 → 20으로 완화 (BWX 같은 ETF·신규상장 대응)
        for yt in candidates:
            for period in periods:
                tried.append(f"{yt}({period})")
                try:
                    h = yf.Ticker(yt).history(period=period, auto_adjust=True)
                    if h is not None and not h.empty and len(h) >= min_rows:
                        hist = h
                        break
                except Exception:
                    continue
            if hist is not None:
                break

        if hist is None or hist.empty or len(hist) < min_rows:
            rows = 0 if hist is None or hist.empty else len(hist)
            return jsonify({
                "error": f"데이터 부족 (시도: {', '.join(tried[:6])} / 확보: {rows}일, 필요: {min_rows}일)"
            }), 404

        analyzer = FourAxisAnalyzer(hist, ticker)
        result = analyzer.analyze()

        # 큰 차트 렌더링 (1200x560) — 2패널(가격+거래량) 구성
        renderer = HandDrawnChartRenderer(
            hist, result, ticker=ticker,
            width_px=1200, height_px=560, dpi=100,
        )
        img = renderer.render()

        # PIL Image → base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        chart_b64 = base64.b64encode(buf.read()).decode("ascii")

        # 4축 분석 데이터 (numpy 타입 → Python 네이티브 변환)
        import json
        import numpy as np

        def _sanitize(obj):
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        rd = _sanitize(result.to_dict())
        return jsonify({
            "chart": chart_b64,
            "phase": rd["phase"],
            "signal_stars": rd["signal_stars"],
            "haiku": rd["haiku"],
            "trend": rd["trend"],
            "momentum": rd["momentum"],
            "volatility": rd["volatility"],
            "volume": rd["volume"],
            "key_observation": rd.get("key_observation", ""),
            "structured_analysis": rd.get("structured_analysis", ""),
        })
    except Exception as e:
        logging.exception("api_four_axis")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
