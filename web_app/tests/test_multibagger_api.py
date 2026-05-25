import os, sys, json, pickle, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app


def test_multibagger_page_renders():
    client = flask_app.app.test_client()
    resp = client.get("/multibagger")
    assert resp.status_code == 200
    assert b"multibagger" in resp.data.lower() or b"\xeb\xa9\x80\xed\x8b\xb0" in resp.data  # "멀티" UTF-8


def test_api_multibagger_returns_warming_when_no_cache(monkeypatch):
    monkeypatch.setattr(flask_app, "_multibagger_results_cache", {})
    client = flask_app.app.test_client()
    resp = client.get("/api/multibagger")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["meta"].get("warming") is True or resp.headers.get("X-Warming-In-Progress") == "true"


def test_api_thresholds():
    client = flask_app.app.test_client()
    resp = client.get("/api/multibagger/thresholds")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "F1_MCAP_MIN" in body


def test_api_ticker_returns_404_when_unknown(monkeypatch):
    monkeypatch.setattr(flask_app, "_multibagger_results_cache", {"data": {"pass": [], "watch": []}, "_ts": time.time()})
    client = flask_app.app.test_client()
    resp = client.get("/api/multibagger/ticker/UNKNOWNSYM")
    assert resp.status_code == 404
