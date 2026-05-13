# -*- coding: utf-8 -*-
"""Telegram Bot API notifier built on urllib.request only."""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def is_configured() -> bool:
    """Return True when Telegram bot token and chat id are present."""
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _result(*, ok: bool, status: int = 0, error: str | None = None, message_id: int | None = None) -> dict:
    return {
        "ok": ok,
        "status": status,
        "error": error,
        "message_id": message_id,
    }


def _format_signal(
    ticker: str,
    score: int,
    grade: str,
    buy_count: int,
    regime: str,
    detail: str | None = None,
) -> str:
    safe_ticker = html.escape(str(ticker))
    safe_regime = html.escape(str(regime))
    safe_grade = html.escape(str(grade))
    detail_line = html.escape(str(detail)) if detail else ""
    lines = [
        f"<b>종목 {safe_ticker}</b>  <code>{safe_regime}</code>",
        f"점수: <b>{int(score)}</b>/100 등급 {safe_grade}",
        f"매수신호 <b>{int(buy_count)}/7</b>",
    ]
    if detail_line:
        lines.append(detail_line)
    return "\n".join(lines)


def send_message(
    text: str,
    *,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    timeout: float = 5.0,
) -> dict:
    """POST sendMessage and return a normalized result dict."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return _result(ok=False, error="not_configured")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": str(text),
        "parse_mode": parse_mode,
        "disable_notification": bool(disable_notification),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            status = getattr(response, "status", response.getcode())
            body = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        message = parsed.get("result") or {}
        return _result(
            ok=bool(parsed.get("ok")),
            status=int(status),
            error=None if parsed.get("ok") else str(parsed.get("description") or "telegram_error"),
            message_id=message.get("message_id"),
        )
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            error = str(parsed.get("description") or body or exc.reason)
        except Exception:
            error = str(exc.reason)
        return _result(ok=False, status=int(exc.code), error=error)
    except Exception as exc:
        return _result(ok=False, error=str(exc) or exc.__class__.__name__)


def send_signal(
    ticker: str,
    score: int,
    grade: str,
    buy_count: int,
    regime: str,
    detail: str | None = None,
) -> dict:
    """Format a stock signal and deliver it through send_message."""
    return send_message(_format_signal(ticker, score, grade, buy_count, regime, detail))


def _run_self_tests() -> None:
    original_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    original_chat_id = os.environ.pop("TELEGRAM_CHAT_ID", None)
    try:
        assert is_configured() is False
        result = send_message("테스트")
        assert result["ok"] is False
        assert result["error"] == "not_configured"

        captured: dict[str, object] = {}
        original_send_message = globals()["send_message"]

        def fake_send_message(
            text: str,
            *,
            parse_mode: str = "HTML",
            disable_notification: bool = False,
            timeout: float = 5.0,
        ) -> dict:
            captured["text"] = text
            captured["parse_mode"] = parse_mode
            captured["disable_notification"] = disable_notification
            captured["timeout"] = timeout
            return _result(ok=True, status=200, message_id=123)

        globals()["send_message"] = fake_send_message
        try:
            signal_result = send_signal("005930", 88, "A", 5, "BULL", "돌파 확인")
        finally:
            globals()["send_message"] = original_send_message

        assert signal_result["ok"] is True
        assert "<b>종목 005930</b>" in str(captured["text"])
        assert "<code>BULL</code>" in str(captured["text"])
        assert "점수: <b>88</b>/100 등급 A" in str(captured["text"])
        assert "매수신호 <b>5/7</b>" in str(captured["text"])
        assert "돌파 확인" in str(captured["text"])
    finally:
        if original_token is not None:
            os.environ["TELEGRAM_BOT_TOKEN"] = original_token
        if original_chat_id is not None:
            os.environ["TELEGRAM_CHAT_ID"] = original_chat_id


if __name__ == "__main__":
    _run_self_tests()
    print("TELEGRAM_NOTIFIER OK")
