import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import history


def test_grade_from_score_cuts():
    assert history._grade_from_score(75) == "S"
    assert history._grade_from_score(74) == "A"
    assert history._grade_from_score(60) == "A"
    assert history._grade_from_score(59) == "B"
    assert history._grade_from_score(45) == "B"
    assert history._grade_from_score(44) == "C"


def test_grade_from_score_invalid():
    assert history._grade_from_score(None) is None
    assert history._grade_from_score("abc") is None
    assert history._grade_from_score("") is None


import json
import importlib
from datetime import date


def _reload_history_with_dir(tmp_path, monkeypatch):
    import history as h
    importlib.reload(h)
    monkeypatch.setattr(h, "_SNAP_DIR", str(tmp_path))
    return h


def test_save_snapshot_includes_entry(tmp_path, monkeypatch):
    h = _reload_history_with_dir(tmp_path, monkeypatch)
    results = [
        {"Ticker": "AAA", "TotalScore": 80, "EntryStatus": "STRONG"},
        {"Ticker": "BBB", "TotalScore": 50},
    ]
    h.save_snapshot(results, "US")
    p = os.path.join(str(tmp_path), f"scanner_US_{date.today().isoformat()}.json")
    with open(p, encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["AAA"]["entry"] == "STRONG"
    assert snap["BBB"]["entry"] is None
    assert snap["AAA"]["score"] == 80.0
