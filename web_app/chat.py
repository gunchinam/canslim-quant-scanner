# -*- coding: utf-8 -*-
"""실시간 익명 채팅 — Flask-SocketIO + SQLite."""
import hashlib, os, random, sqlite3, time, threading
from flask_socketio import SocketIO, emit

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chat.db")
_db_lock = threading.Lock()

# ── 랜덤 닉네임 생성 ─────────────────────────────────────────────────
_ADJ = [
    "급등하는", "폭락하는", "횡보하는", "눌림목의", "돌파하는",
    "존버하는", "풀매수한", "손절한", "물타는", "익절한",
    "갭상한", "역배열", "정배열", "눌림의", "쌍바닥",
    "상한가", "하한가", "데드캣", "골든크로스", "데크의",
    "배당받는", "공매도한", "추격매수", "분할매수", "기다리는",
]
_NOUN = [
    "개미", "세력", "작전주", "슈퍼개미", "큰손",
    "단타충", "장투러", "차트쟁이", "뉴비", "고수",
    "주린이", "코린이", "영끌러", "빚투러", "가치투자자",
    "모멘텀러", "스윙러", "스캘퍼", "퀀트", "AI봇",
    "외인", "기관", "사모펀드", "헤지펀드", "개미왕",
]

def _random_nick() -> str:
    return f"{random.choice(_ADJ)}{random.choice(_NOUN)}"

# ── DB ────────────────────────────────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        sid TEXT NOT NULL,
        nick TEXT NOT NULL,
        msg TEXT NOT NULL
    )""")
    conn.commit()
    return conn

# 시작 시 테이블 생성
_get_db().close()

# sid → nickname 매핑
_nicks: dict[str, str] = {}
_online: int = 0
_online_lock = threading.Lock()

def _recent_messages(limit=50) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT ts, nick, msg FROM messages ORDER BY id DESC LIMIT ?", (limit,)
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

# ── SocketIO 이벤트 ───────────────────────────────────────────────────
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
    # 최근 메시지 전송
    emit("init", {"nick": nick, "history": _recent_messages(), "online": cnt})
    # 입장 알림
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
