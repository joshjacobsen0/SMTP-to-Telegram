"""Minimal Telegram Bot API client (stdlib only)."""

from __future__ import annotations

import json
import logging
import mimetypes
import urllib.error
import urllib.request
import uuid

import config

log = logging.getLogger("telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
MAX_TEXT_LENGTH = 4096


def _api_url(method: str) -> str:
    return API_BASE.format(token=config.TELEGRAM_BOT_TOKEN, method=method)


def _post(method: str, data: bytes, content_type: str) -> None:
    req = urllib.request.Request(
        _api_url(method),
        data=data,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        log.error("Telegram API %s returned HTTP %s: %s", method, exc.code, body.decode(errors="replace"))
        return
    except urllib.error.URLError as exc:
        log.error("Telegram API %s failed: %s", method, exc)
        return

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        log.error("Telegram API %s returned non-JSON response: %s", method, body[:200])
        return

    if not result.get("ok"):
        log.error("Telegram API %s failed: %s", method, result)


def _chunk_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


def send_message(text: str) -> None:
    for chunk in _chunk_text(text):
        payload = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": chunk}).encode("utf-8")
        _post("sendMessage", payload, "application/json")


def send_document(filename: str, content: bytes, caption: str = "") -> None:
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts = []
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{config.TELEGRAM_CHAT_ID}\r\n".encode("utf-8")
    )
    if caption:
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n".encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)
    _post("sendDocument", body, f"multipart/form-data; boundary={boundary}")
