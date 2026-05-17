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
import json
import logging
import subprocess
import threading
import queue
import time
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))

# 프로젝트 루트 경로 (four_axis_analyzer, handdrawn_renderer 접근용)
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from flask import Flask, request, jsonify, render_template
from engine_adapter import ScanAdapter
from one_liner import annotate as annotate_one_liners
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

_AI_COMMENT_TTL_SEC = 3600
_ai_comment_cache: dict[tuple[str, str, str], dict[str, object]] = {}
_ai_comment_cache_lock = threading.Lock()


def _build_yf_candidates(ticker: str, market: str) -> list[str]:
    raw = (ticker or "").strip()
    market = (market or "US").upper()

    if market == "US":
        tu = raw.upper()
        candidates = [raw, tu]
        if "." in tu:
            candidates += [tu.replace(".", "-"), raw.replace(".", "-")]
        if "-" in tu:
            candidates += [tu.replace("-", "."), raw.replace("-", ".")]
    else:
        base = raw
        kept_suf = None
        for suf in (".KS", ".KQ", ".ks", ".kq"):
            if base.endswith(suf):
                kept_suf = suf.upper()
                base = base[:-len(suf)]
                break
        t6 = base.zfill(6) if base.isdigit() else base
        if kept_suf in (".KS", ".KQ"):
            other = ".KQ" if kept_suf == ".KS" else ".KS"
            candidates = [f"{t6}{kept_suf}", f"{t6}{other}"]
        else:
            candidates = [f"{t6}.KS", f"{t6}.KQ"]

    seen = set()
    return [c for c in candidates if c and not (c in seen or seen.add(c))]


def _make_adapter() -> ScanAdapter:
    market   = request.args.get("market",   "US")
    strategy = request.args.get("strategy", "BALANCED")
    return ScanAdapter(market=market, strategy=strategy)


def _get_config_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(str(raw).strip()) if raw is not None and str(raw).strip() != "" else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _run_with_timeout(func, timeout_sec: int, label: str):
    q: queue.Queue = queue.Queue(maxsize=1)

    def _worker():
        try:
            q.put((True, func()))
        except Exception as exc:
            q.put((False, exc))

    t = threading.Thread(target=_worker, daemon=True, name=f"{label}-worker")
    t.start()
    t.join(timeout=max(1, int(timeout_sec)))
    if t.is_alive():
        raise TimeoutError(f"{label} timed out after {timeout_sec}s")
    ok, payload = q.get()
    if ok:
        return payload
    raise payload


def _strip_kr_suffix(ticker: str) -> str:
    raw = (ticker or "").strip()
    for suf in (".KS", ".KQ", ".ks", ".kq"):
        if raw.endswith(suf):
            return raw[:-len(suf)]
    return raw


def _cache_get_ai_comment(key: tuple[str, str, str]) -> dict[str, object] | None:
    now = int(time.time())
    with _ai_comment_cache_lock:
        cached = _ai_comment_cache.get(key)
        if not cached:
            return None
        ts = int(cached.get("ts", 0) or 0)
        if now - ts > _AI_COMMENT_TTL_SEC:
            _ai_comment_cache.pop(key, None)
            return None
        return cached


def _cache_set_ai_comment(key: tuple[str, str, str], comment: str) -> dict[str, object]:
    payload = {"comment": comment, "ts": int(time.time())}
    with _ai_comment_cache_lock:
        _ai_comment_cache[key] = payload
    return payload


def _build_ai_comment_prompt(ticker: str, market: str, metrics: dict) -> str:
    payload = {
        "Ticker": metrics.get("Ticker") or ticker,
        "Name": metrics.get("Name"),
        "Market": market,
        "Sector": metrics.get("Sector"),
        "TotalScore": metrics.get("TotalScore"),
        "Signal": metrics.get("Signal"),
        "Conviction": metrics.get("Conviction"),
        "Price": metrics.get("Price"),
        "DayChg": metrics.get("DayChg"),
        "RSI": metrics.get("RSI"),
        "Mom12M": metrics.get("Mom12M"),
        "Mom3M": metrics.get("_Mom3M", metrics.get("Mom3M")),
        "PER": metrics.get("_PER"),
        "ROE": metrics.get("_ROE"),
        "EPSGrowth": metrics.get("_EPSGrowth"),
        "RSRating": metrics.get("RSRating"),
        "EntryStatus": metrics.get("EntryStatus"),
        "EntryScore": metrics.get("EntryScore"),
        "TargetPrice": metrics.get("TargetPrice"),
        "BrokerTarget": metrics.get("BrokerTarget"),
        "TopReason": metrics.get("TopReason"),
        "OneLiner": metrics.get("OneLiner"),
        "Desc": metrics.get("Desc"),
    }
    return (
        "당신은 한국어로 답하는 주식 애널리스트다.\n"
        "아래 지표만 바탕으로 2~3문장 코멘트를 작성하라.\n"
        "- 밸류에이션, 모멘텀, 리스크를 모두 언급할 것\n"
        "- 불릿 금지, 문장형으로만 작성\n"
        "- 과도한 확신 표현과 투자 권유 문구는 피할 것\n"
        "- 160자 안팎으로 간결하게 작성할 것\n\n"
        f"종목 지표 JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _call_ai_comment_llm(prompt: str) -> str:
    openai_key    = (os.environ.get("OPENAI_API_KEY") or "").strip()
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    grok_key      = (os.environ.get("GROK_API_KEY") or "").strip()
    pref          = (os.environ.get("AI_COMMENT_PROVIDER") or "").strip().lower()

    # 우선순위: 명시된 pref → 첫 번째로 키가 있는 provider
    order = []
    if pref in ("openai", "anthropic", "grok"):
        order.append(pref)
    for p in ("openai", "anthropic", "grok"):
        if p not in order: order.append(p)
    provider = None
    for p in order:
        if p == "openai" and openai_key: provider = "openai"; break
        if p == "anthropic" and anthropic_key: provider = "anthropic"; break
        if p == "grok" and grok_key: provider = "grok"; break

    if provider == "openai":
        model = (os.environ.get("AI_COMMENT_OPENAI_MODEL") or "gpt-4o-mini").strip()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(
                {
                    "model": model,
                    "temperature": 0.4,
                    "max_tokens": 220,
                    "messages": [
                        {"role": "system", "content": "한국어로 간결한 주식 코멘트를 작성해라."},
                        {"role": "user", "content": prompt},
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        comment = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
    elif provider == "anthropic":
        model = (os.environ.get("AI_COMMENT_ANTHROPIC_MODEL") or "claude-3-5-haiku-latest").strip()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(
                {
                    "model": model,
                    "max_tokens": 220,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = data.get("content") or []
        comment = " ".join(
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        )
    elif provider == "grok":
        model = (os.environ.get("AI_COMMENT_GROK_MODEL") or "grok-2-latest").strip()
        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions",
            data=json.dumps(
                {
                    "model": model,
                    "temperature": 0.4,
                    "max_tokens": 220,
                    "messages": [
                        {"role": "system", "content": "한국어로 간결한 주식 코멘트를 작성해라."},
                        {"role": "user", "content": prompt},
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {grok_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        comment = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
    else:
        raise RuntimeError("LLM API key not configured")

    text = " ".join(str(comment or "").split())
    if not text:
        raise RuntimeError("Empty AI comment response")
    return text


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


@app.route("/compare")
def compare_page():
    raw = request.args.get("tickers", "")
    tickers = [tk.strip() for tk in raw.split(",") if tk.strip()][:4]
    market = (request.args.get("market") or "US").upper()
    return render_template("compare.html", tickers=tickers, market=market)


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
    """?? ?? ? ????? ?? ??."""
    try:
        incoming = request.get_json(force=True) or {}
        existing = load_config()
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
    """?? ???."""
    try:
        save_config({})
        return jsonify({"ok": True})
    except Exception as e:
        logging.exception("api_settings_delete")
        return jsonify({"ok": False, "error": str(e)}), 500


# ?? JSON API ?????????????????????????????????????????????????????????????

@app.route("/api/sectors")
def api_sectors():
    """GET /api/sectors?market=US ? {"sectors": {???: [ticker, ...]}}"""
    try:
        adapter = _make_adapter()
        return jsonify({
            "sectors": adapter.get_sectors(),
            "groups":  adapter.get_sector_groups(),
        })
    except Exception as e:
        logging.exception("api_sectors")
        return jsonify({"error": str(e)}), 500


def _apply_aq_fusion(results: list, market: str, top_n: int = 30) -> list:
    """상위 TotalScore N개에 대해 AgentQuant 점수 융합 (순차 호출, 32-bit Python 안정성).
    동시 호출 시 yfinance+pandas 메모리 충돌로 힙 손상(0xC0000374) 발생 가능 → 직렬 처리.
    """
    if not results:
        return results
    try:
        from agentquant_signal import get_regime_signal
    except Exception as exc:
        logging.warning("agentquant import skipped: %s", exc)
        return results

    ranked = sorted(
        [r for r in results if isinstance(r, dict)],
        key=lambda r: (r.get("TotalScore") or 0),
        reverse=True,
    )[:top_n]

    aq_map: dict[str, dict] = {}
    for row in ranked:
        tk = row.get("Ticker") or row.get("ticker")
        if not tk:
            continue
        try:
            sig = get_regime_signal(tk, market=market)
            if sig:
                aq_map[tk] = sig
        except Exception as exc:
            logging.debug("aq fetch failed %s: %s", tk, exc)
            continue

    for r in results:
        tk = r.get("Ticker") or r.get("ticker")
        aq = aq_map.get(tk)
        if not aq or not aq.get("stock"):
            continue
        try:
            aq_score = float(aq["stock"].get("score") or 0)
            base = r.get("EntryScore")
            base_f = float(base) if base is not None else None
            fused = round(0.6 * base_f + 0.4 * aq_score, 1) if base_f is not None else round(aq_score, 1)
            r["EntryScore_engine"] = base_f
            r["EntryScore_aq"] = aq_score
            r["EntryScore"] = fused
            r["AQ_Verdict"] = aq["stock"].get("verdict_kr")
            r["AQ_VerdictCode"] = aq["stock"].get("verdict")
            r["AQ_Regime"] = aq.get("market", {}).get("label")
        except Exception:
            continue
    return results


@app.route("/api/scan")
def api_scan():
    """GET /api/scan?market=US&strategy=BALANCED&sector=SaaS → [{...}, ...]"""
    try:
        adapter = _make_adapter()
        sector  = request.args.get("sector", "")
        market  = (request.args.get("market") or "US").upper()
        # 기본 0 — 32-bit Python 환경 안정성 우선. ?aq_top=10 또는 env AQ_SCAN_TOP 로 활성화.
        try:
            aq_top = int(request.args.get("aq_top", os.environ.get("AQ_SCAN_TOP", "0")))
        except (TypeError, ValueError):
            aq_top = 0
        results = adapter.scan_sector(sector) if sector else adapter.scan_all()
        # 히스토리 델타 주석/스냅샷 저장
        try:
            import history
            results = history.annotate_deltas(results, market)
            # 섹터 스캔이 아닐 때만 스냅샷 저장 (전체 스캔만 저장)
            if not sector:
                history.save_snapshot(results, market)
        except Exception as he:
            logging.warning("history annotate/save failed: %s", he)
        # 촌철살인 한줄평 추가
        try:
            results = annotate_one_liners(results)
        except Exception as oe:
            logging.warning("one_liner annotate failed: %s", oe)
        # AgentQuant 융합 (상위 N개)
        if aq_top > 0:
            try:
                results = _apply_aq_fusion(results, market, top_n=aq_top)
            except Exception as ae:
                logging.warning("aq fusion failed: %s", ae)
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
            return jsonify({"error": "해당 티커의 데이터를 찾을 수 없습니다."}), 404
        try:
            result = annotate_one_liners([result])[0]
        except Exception as oe:
            logging.warning("one_liner annotate (ticker) failed: %s", oe)
        # AgentQuant 진입 점수 융합 (가중치 0.6 기존 / 0.4 AQ)
        try:
            from agentquant_signal import get_regime_signal
            market = (request.args.get("market") or "US").upper()
            aq = get_regime_signal(ticker, market=market)
            if aq and aq.get("stock"):
                aq_score = float(aq["stock"].get("score") or 0)
                base = result.get("EntryScore")
                base_f = float(base) if base is not None else None
                if base_f is not None:
                    fused = round(0.6 * base_f + 0.4 * aq_score, 1)
                else:
                    fused = round(aq_score, 1)
                result["EntryScore_engine"] = base_f
                result["EntryScore_aq"] = aq_score
                result["EntryScore"] = fused
                result["AQ_Verdict"] = aq["stock"].get("verdict_kr")
                result["AQ_VerdictCode"] = aq["stock"].get("verdict")
                result["AQ_Regime"] = aq.get("market", {}).get("label")
                result["AQ_Reasons"] = aq["stock"].get("reasons", [])[:4]
        except Exception as aqe:
            logging.warning("agentquant fuse failed for %s: %s", ticker, aqe)
        return jsonify(result)
    except Exception as e:
        logging.exception("api_ticker")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai_comment/<ticker>")
def api_ai_comment(ticker: str):
    market = (request.args.get("market") or "US").upper()
    strategy = request.args.get("strategy", "BALANCED")
    cache_key = (market, strategy, (ticker or "").upper())

    cached = _cache_get_ai_comment(cache_key)
    if cached:
        return jsonify(cached)

    try:
        adapter = ScanAdapter(market=market, strategy=strategy)
        result = adapter.analyze_ticker(ticker)
        if result is None:
            return jsonify({"error": "종목 데이터를 찾을 수 없습니다."}), 404

        prompt = _build_ai_comment_prompt(ticker, market, result)
        comment = _call_ai_comment_llm(prompt)
        return jsonify(_cache_set_ai_comment(cache_key, comment))
    except Exception as e:
        logging.warning("api_ai_comment failed for %s: %s", ticker, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/consensus/<ticker>")
def api_consensus(ticker: str):
    """??? ???? ??: ??? ??, ??/??, ?? ???."""
    import urllib.request
    import json as _json

    market = (request.args.get("market") or "US").upper()
    result = {"summary": {}, "reports": []}

    if market == "KR":
        code = ticker.split('.')[0].zfill(6)
        _ua = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        def _int(v):
            try: return int(str(v).replace(',', ''))
            except: return 0

        # 1) integration API ? ???? ?? (??/??/??/??)
        try:
            url = f"https://m.stock.naver.com/api/stock/{code}/integration"
            req = urllib.request.Request(url, headers=_ua)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
            ci = data.get('consensusInfo') or {}
            result["summary"] = {
                "mean":    _int(ci.get('priceTargetMean', '')),
                "high":    _int(ci.get('priceTargetHigh', '')),
                "low":     _int(ci.get('priceTargetLow', '')),
                "count":   _int(ci.get('targetPriceCount', '') or ci.get('consensusCount', '') or ci.get('stockFirmCount', '')),
                "opinion": ci.get('investmentOpinion', ''),
            }
        except Exception as e:
            logging.warning("consensus integration: %s", e)

        # 2) research API ? ?? ??? ???
        for ep in [
            f"https://m.stock.naver.com/api/stock/{code}/finance/research?pageSize=5",
            f"https://m.stock.naver.com/api/stock/{code}/research?pageSize=5",
        ]:
            try:
                req2 = urllib.request.Request(ep, headers=_ua)
                with urllib.request.urlopen(req2, timeout=5) as resp2:
                    rd = _json.loads(resp2.read().decode('utf-8'))
                items = rd if isinstance(rd, list) else (rd.get('list') or rd.get('reports') or rd.get('items') or [])
                for it in items[:5]:
                    firm = it.get('stockFirmName','') or it.get('brokerName','') or it.get('provider','')
                    tp   = it.get('priceTarget','') or it.get('targetPrice','')
                    if firm:
                        result["reports"].append({
                            'firm':    firm,
                            'target':  _int(tp),
                            'date':    it.get('date','') or it.get('writeDate',''),
                            'opinion': it.get('investmentOpinion','') or it.get('opinion',''),
                        })
                if result["reports"]:
                    break
            except Exception:
                continue

    else:  # US ? yfinance ??? (?? broker ???? ??)
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            def _flt(v):
                try: return float(v)
                except: return 0
            result["summary"] = {
                "mean":    _flt(info.get("targetMeanPrice", 0)),
                "high":    _flt(info.get("targetHighPrice", 0)),
                "low":     _flt(info.get("targetLowPrice", 0)),
                "count":   int(info.get("numberOfAnalystOpinions", 0) or 0),
                "opinion": info.get("recommendationKey", ""),
            }
        except Exception as e:
            logging.warning("yfinance consensus: %s", e)

    return jsonify(result)

@app.route("/api/regime/<ticker>")
def api_regime(ticker: str):
    """AgentQuant 기반 시장 레짐 + 진입 타이밍 시그널."""
    market = (request.args.get("market") or "US").upper()
    try:
        from agentquant_signal import get_regime_signal
        payload = get_regime_signal(ticker, market=market)
        if not payload:
            return jsonify({"error": "신호를 계산할 수 없습니다."}), 404
        return jsonify(payload)
    except Exception as e:
        logging.exception("api_regime")
        return jsonify({"error": str(e)}), 500


@app.route("/api/four_axis/<ticker>")
def api_four_axis(ticker: str):
    """4축 핸드드로윙 차트 + 분석 데이터 반환 (base64 PNG)."""
    try:
        import yfinance as yf
        from four_axis_analyzer import FourAxisAnalyzer
        from handdrawn_renderer import HandDrawnChartRenderer

        market = (request.args.get("market") or "US").upper()
        candidates = _build_yf_candidates(ticker, market)
        fetch_timeout_sec = _get_config_int("FOUR_AXIS_FETCH_TIMEOUT_SEC", 20, minimum=5, maximum=120)
        info_timeout_sec = _get_config_int("FOUR_AXIS_INFO_TIMEOUT_SEC", 8, minimum=3, maximum=60)
        min_rows = _get_config_int("FOUR_AXIS_MIN_ROWS", 20, minimum=10, maximum=252)

        # 다중 기간 폴백 — 2y → 1y → 6mo → 3mo 순으로 시도
        # 일부 ETF/저유동 종목은 1y로는 비어있고 6mo 이하에서만 데이터가 나오기도 함
        hist = None
        tried = []
        periods = ("2y", "1y", "6mo", "3mo")
        for yt in candidates:
            for period in periods:
                tried.append(f"{yt}({period})")
                try:
                    h = _run_with_timeout(
                        lambda yt=yt, period=period: yf.Ticker(yt).history(
                            period=period,
                            auto_adjust=True,
                            timeout=fetch_timeout_sec,
                        ),
                        fetch_timeout_sec,
                        f"four_axis history {yt} {period}",
                    )
                    if h is not None and not h.empty and len(h) >= min_rows:
                        hist = h
                        break
                except Exception as exc:
                    logging.warning("four_axis history fetch failed: %s", exc)
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

        # 차트 제목에 종목명 표시 (티커 코드 대신).
        # KR 우선순위: kr_company_info → yfinance longName/shortName → 티커 폴백.
        chart_title = ""
        try:
            if market == "KR":
                try:
                    from swing_scan.config import stock_names as _sn
                    code6 = _strip_kr_suffix(ticker).zfill(6)
                    nm = _sn.get_name(code6)
                    if nm and nm != code6:
                        chart_title = str(nm)
                except Exception:
                    pass
            # yf.Ticker(...).info 호출은 매우 느리고 hang 위험이 큼.
            # KR은 stock_names 미스 시 ticker 폴백 (info 호출 안 함).
            # US만 보조 폴백으로 info 사용.
            if not chart_title and market == "US":
                try:
                    yt0 = candidates[0] if candidates else ticker
                    yinfo = _run_with_timeout(
                        lambda yt0=yt0: yf.Ticker(yt0).info or {},
                        info_timeout_sec,
                        f"four_axis info {yt0}",
                    )
                    chart_title = (yinfo.get("longName")
                                   or yinfo.get("shortName") or "")
                except Exception:
                    pass
        except Exception:
            pass
        chart_title = chart_title or ticker

        # 큰 차트 렌더링 (1200x560) — 2패널(가격+거래량) 구성
        renderer = HandDrawnChartRenderer(
            hist, result, ticker=chart_title,
            width_px=1200, height_px=560, dpi=100,
        )
        img = renderer.render()

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        chart_b64 = base64.b64encode(buf.read()).decode("ascii")

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


# ── 공시·뉴스 API (DART + Naver News) ─────────────────────────────────

@app.route("/api/dart-news/<ticker>")
def api_dart_news(ticker: str):
    """KR 종목 공시 목록 + 뉴스 감성분석 결합 반환."""
    market = (request.args.get("market") or "US").upper()
    if market != "KR":
        return jsonify({"error": "KR 종목만 지원"}), 400

    code = ticker.split(".")[0].zfill(6)
    result = {"filings": [], "news": {}, "dart_available": False, "news_available": False}

    # 1) DART 공시
    try:
        import dart_api
        if dart_api.is_available():
            result["dart_available"] = True
            result["filings"] = dart_api.get_filings(code, count=10)
    except Exception as e:
        logging.warning("dart-news filings: %s", e)

    # 2) Naver News 감성분석 — 종목명으로 검색
    try:
        import naver_news
        if naver_news.is_available():
            result["news_available"] = True
            # 종목명 가져오기
            stock_name = ""
            try:
                from swing_scan.config import stock_names as _sn
                stock_name = _sn.get_name(code)
                if stock_name == code:
                    stock_name = ""
            except Exception:
                pass
            if not stock_name:
                try:
                    import dart_api as _da
                    s = _da.get_summary(code)
                    if s.get("available"):
                        stock_name = s["data"].get("corp_name", "")
                except Exception:
                    pass
            if stock_name:
                result["news"] = naver_news.summarize(stock_name, limit=15)
    except Exception as e:
        logging.warning("dart-news sentiment: %s", e)

    return jsonify(result)


# ── US 인사이트 API (yfinance + SEC EDGAR) ────────────────────────────

_sec_cik_map: dict = {}  # ticker → CIK 캐시


def _load_sec_cik_map() -> dict:
    """SEC company_tickers.json에서 ticker→CIK 매핑을 다운로드(첫 호출 시 1회)."""
    global _sec_cik_map
    if _sec_cik_map:
        return _sec_cik_map
    import json as _json
    import gzip as _gzip
    url = "https://www.sec.gov/files/company_tickers.json"
    req = urllib.request.Request(url, headers={
        "User-Agent": "StockScanner admin@example.com",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            if raw[:2] == b'\x1f\x8b':
                raw = _gzip.decompress(raw)
            data = _json.loads(raw.decode("utf-8"))
        for entry in data.values():
            tk = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str", "")
            if tk and cik:
                _sec_cik_map[tk] = str(cik).zfill(10)
    except Exception as e:
        logging.warning("SEC CIK map load failed: %s", e)
    return _sec_cik_map


def _get_sec_filings(ticker: str, count: int = 10) -> list:
    """SEC EDGAR에서 최근 공시(10-K/10-Q/8-K) 조회."""
    import json as _json
    cik_map = _load_sec_cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    req = urllib.request.Request(url, headers={
        "User-Agent": "StockScanner admin@example.com",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read().decode("utf-8"))
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        names = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])
        results = []
        target_forms = {"10-K", "10-Q", "8-K", "10-K/A", "10-Q/A"}
        for i in range(len(forms)):
            if forms[i] not in target_forms:
                continue
            acc = accessions[i].replace("-", "") if i < len(accessions) else ""
            doc = names[i] if i < len(names) else ""
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/{doc}" if acc and doc else ""
            results.append({
                "form": forms[i],
                "date": dates[i] if i < len(dates) else "",
                "description": descriptions[i] if i < len(descriptions) else forms[i],
                "url": filing_url,
            })
            if len(results) >= count:
                break
        return results
    except Exception as e:
        logging.warning("SEC filings fetch: %s", e)
        return []


@app.route("/api/us-insight/<ticker>")
def api_us_insight(ticker: str):
    """US 종목 인사이트: 뉴스 감성 + 기관보유/공매도 + 어닝캘린더 + SEC 공시."""
    market = (request.args.get("market") or "US").upper()
    if market != "US":
        return jsonify({"error": "US 종목만 지원"}), 400

    result = {
        "news": {}, "holders": {}, "earnings": {},
        "recommendations": [], "sec_filings": [],
        "news_available": False, "holders_available": False,
        "earnings_available": False, "sec_available": False,
    }

    # 1) Yahoo Finance 뉴스 감성분석
    try:
        import news_summarizer
        news_data = news_summarizer.summarize(ticker, limit=10)
        if news_data.get("count", 0) > 0:
            result["news_available"] = True
        result["news"] = news_data
    except Exception as e:
        logging.warning("us-insight news: %s", e)

    # 2) 기관보유 + 공매도
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        holders = {
            "institutional_pct": info.get("heldPercentInstitutions"),
            "insider_pct": info.get("heldPercentInsiders"),
            "short_pct": info.get("shortPercentOfFloat"),
            "short_ratio": info.get("shortRatio"),
        }
        if any(v is not None for v in holders.values()):
            result["holders_available"] = True
            # float 변환
            for k, v in holders.items():
                if v is not None:
                    try:
                        holders[k] = round(float(v), 4)
                    except (TypeError, ValueError):
                        holders[k] = None
        result["holders"] = holders

        # 3) 애널리스트 추천 이력 (upgrades_downgrades)
        try:
            ud = yf.Ticker(ticker).upgrades_downgrades
            if ud is not None and len(ud) > 0:
                rec_list = []
                for _, row in ud.head(8).iterrows():
                    rec_list.append({
                        "firm": str(row.get("Firm", "")),
                        "grade": str(row.get("ToGrade", "")),
                        "from_grade": str(row.get("FromGrade", "")),
                        "action": str(row.get("Action", "")),
                        "target": row.get("currentPriceTarget"),
                        "prior_target": row.get("priorPriceTarget"),
                    })
                result["recommendations"] = rec_list
        except Exception:
            pass
    except Exception as e:
        logging.warning("us-insight holders: %s", e)

    # 4) 어닝 캘린더
    try:
        import event_calendar
        dday, date_str = event_calendar.earnings_dday(ticker)
        if dday is not None:
            result["earnings_available"] = True
            chip = event_calendar.build_dday_chip(dday)
            result["earnings"] = {
                "dday": dday, "date": date_str,
                "chip_text": chip["text"], "chip_fg": chip["fg"],
                "chip_bg": chip["bg"], "chip_show": chip["show"],
            }
    except Exception as e:
        logging.warning("us-insight earnings: %s", e)

    # 5) SEC EDGAR 공시
    try:
        filings = _get_sec_filings(ticker, count=10)
        if filings:
            result["sec_available"] = True
            result["sec_filings"] = filings
    except Exception as e:
        logging.warning("us-insight sec: %s", e)

    return jsonify(result)


# ── SWING-MOM 스캔 알리미 백그라운드 프로세스 ──────────────────────────
_swing_proc: subprocess.Popen | None = None
_swing_lock = threading.Lock()


_SWING_PID_FILE = os.path.join(_BASE, ".swing_scanner.pid")


def _kill_orphan_scanner():
    """이전 실행에서 남은 고아 프로세스 정리."""
    if not os.path.exists(_SWING_PID_FILE):
        return
    try:
        with open(_SWING_PID_FILE) as f:
            old_pid = int(f.read().strip())
        # 프로세스가 살아있으면 종료
        import signal
        os.kill(old_pid, signal.SIGTERM)
        logging.info("고아 스캔 프로세스 종료 (PID %d)", old_pid)
    except (ProcessLookupError, ValueError, OSError):
        pass  # 이미 죽었거나 유효하지 않은 PID
    try:
        os.remove(_SWING_PID_FILE)
    except OSError:
        pass


def _is_swing_scan_window() -> bool:
    """스캔 알리미를 가동할 수 있는 시간/요일 여부.
    한국 평일 09:00~15:30 만 True. 그 외에는 텔레그램 스팸 방지를 위해 미가동."""
    from datetime import datetime as _dt
    now = _dt.now()
    if now.weekday() >= 5:
        return False
    hhmm = now.strftime("%H:%M")
    return "09:00" <= hhmm < "15:30"


def _start_swing_scanner():
    """SWING-MOM 스캔 알리미를 백그라운드 서브프로세스로 실행."""
    global _swing_proc
    script = os.path.join(_BASE, "swing_scan", "scripts", "swing_mom_scan_alert.py")
    if not os.path.exists(script):
        logging.warning("swing_mom_scan_alert.py 미존재 — 스캔 알리미 비활성")
        return
    if not _is_swing_scan_window():
        logging.info("스캔 윈도우 외 — swing scanner 부팅 스킵 (텔레그램 스팸 방지)")
        # stale PID 파일은 정리
        try:
            if os.path.exists(_SWING_PID_FILE):
                os.remove(_SWING_PID_FILE)
        except OSError:
            pass
        return
    with _swing_lock:
        if _swing_proc and _swing_proc.poll() is None:
            return  # 이미 실행 중
        _kill_orphan_scanner()
        try:
            _swing_log = os.path.join(_BASE, "swing_scan", "logs")
            os.makedirs(_swing_log, exist_ok=True)
            _log_f = open(os.path.join(_swing_log, "scan_alert_bg.log"), "a", encoding="utf-8")
            _env = os.environ.copy()
            _env["NO_COLOR"] = "1"          # Python 3.14 argparse 컬러 충돌 방지
            _env["PYTHONIOENCODING"] = "utf-8"
            _swing_proc = subprocess.Popen(
                [sys.executable, script],
                cwd=_BASE,
                stdout=_log_f,
                stderr=_log_f,
                env=_env,
            )
            # PID 파일 기록
            with open(_SWING_PID_FILE, "w") as f:
                f.write(str(_swing_proc.pid))
            logging.info("SWING-MOM 스캔 알리미 시작 (PID %d)", _swing_proc.pid)
        except Exception as e:
            logging.warning("SWING-MOM 스캔 알리미 실행 실패: %s", e)


def _stop_swing_scanner():
    """백그라운드 스캔 프로세스 종료."""
    global _swing_proc
    with _swing_lock:
        if _swing_proc and _swing_proc.poll() is None:
            _swing_proc.terminate()
            try:
                _swing_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _swing_proc.kill()
            logging.info("SWING-MOM 스캔 알리미 종료")
            _swing_proc = None
        try:
            os.remove(_SWING_PID_FILE)
        except OSError:
            pass


@app.route("/api/swing-scanner", methods=["GET"])
def api_swing_scanner_status():
    """SWING-MOM 스캔 알리미 상태 조회."""
    with _swing_lock:
        running = _swing_proc is not None and _swing_proc.poll() is None
    return jsonify({"running": running, "pid": _swing_proc.pid if running else None})


@app.route("/api/swing-scanner/start", methods=["POST"])
def api_swing_scanner_start():
    _start_swing_scanner()
    return jsonify({"ok": True})


@app.route("/api/swing-scanner/stop", methods=["POST"])
def api_swing_scanner_stop():
    _stop_swing_scanner()
    return jsonify({"ok": True})


import atexit
atexit.register(_stop_swing_scanner)


if __name__ == "__main__":
    # debug 모드 리로더에 의한 중복 실행 방지
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        _start_swing_scanner()
    app.run(debug=True, port=5000, host="0.0.0.0")
