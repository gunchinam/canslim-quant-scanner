# -*- coding: utf-8 -*-
"""Realtime anonymous chat backed by SQLite.

This module degrades gracefully when `flask_socketio` is unavailable so the
rest of the Flask app can still boot and serve scan APIs.
"""

import logging
import os
import random
import sqlite3
import threading
import time

try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(cors_allowed_origins="*")
except Exception as e:
    logging.warning("flask_socketio unavailable; chat disabled: %s", e)

    def emit(*_args, **_kwargs):
        return None

    class _SocketIODummy:
        def init_app(self, app, *args, **kwargs):
            app.logger.warning("SocketIO disabled; chat features are unavailable.")

        def on(self, *_args, **_kwargs):
            def _decorator(fn):
                return fn
            return _decorator

        def run(self, app, *args, **kwargs):
            kwargs.pop("allow_unsafe_werkzeug", None)
            app.run(*args, **kwargs)

    socketio = _SocketIODummy()


_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chat.db")
_db_lock = threading.Lock()

_ADJ = [
    "급등노리는",
    "차분한",
    "눌림보는",
    "돌파추적",
    "관망중인",
    "분할매수",
    "추세추종",
    "모멘텀찾는",
]

_NOUN = [
    "트레이더",
    "투자자",
    "고수",
    "개미",
    "차트러",
    "스캐너",
    "매매러",
    "관찰자",
]


def _random_nick() -> str:
    return f"{random.choice(_ADJ)}{random.choice(_NOUN)}"


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        sid TEXT NOT NULL,
        nick TEXT NOT NULL,
        msg TEXT NOT NULL
    )"""
    )
    conn.commit()
    return conn


_get_db().close()

_nicks: dict[str, str] = {}
_online: int = 0
_online_lock = threading.Lock()


def _recent_messages(limit=50) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT ts, nick, msg FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return [{"ts": r[0], "nick": r[1], "msg": r[2]} for r in reversed(rows)]


def _save_message(sid: str, nick: str, msg: str):
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO messages (ts, sid, nick, msg) VALUES (?, ?, ?, ?)",
            (time.time(), sid, nick, msg),
        )
        conn.commit()
        conn.close()


@socketio.on("connect")
def on_connect():
    from flask import request

    global _online
    sid = request.sid
    nick = _random_nick()
    _nicks[sid] = nick
    with _online_lock:
        _online += 1
        cnt = _online
    emit("init", {"nick": nick, "history": _recent_messages(), "online": cnt})
    emit("system", {"msg": f"{nick} 입장", "online": cnt}, broadcast=True)


@socketio.on("disconnect")
def on_disconnect():
    from flask import request

    global _online
    sid = request.sid
    nick = _nicks.pop(sid, "?")
    with _online_lock:
        _online = max(0, _online - 1)
        cnt = _online
    emit("system", {"msg": f"{nick} 퇴장", "online": cnt}, broadcast=True)


@socketio.on("chat")
def on_chat(data):
    from flask import request

    sid = request.sid
    nick = _nicks.get(sid, "익명")
    msg = (data.get("msg") or "").strip()
    if not msg or len(msg) > 500:
        return
    _save_message(sid, nick, msg)
    emit("chat", {"ts": time.time(), "nick": nick, "msg": msg}, broadcast=True)
