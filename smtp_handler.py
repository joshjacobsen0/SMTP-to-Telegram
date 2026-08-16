"""SMTP handler: parses incoming mail and forwards it to Telegram."""

from __future__ import annotations

import asyncio
import logging
from email import message_from_bytes, policy

import telegram

log = logging.getLogger("smtp")

MAX_ATTACHMENT_SIZE = 45 * 1024 * 1024  # stay under Telegram's ~50 MB bot upload limit


def accept_all_auth(mechanism, login, password):
    """Accept any AUTH attempt without checking credentials (auth strength is not a goal here)."""
    return True


def _extract_body(msg) -> str:
    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is None:
        return "(no readable body)"
    content = body_part.get_content()
    if body_part.get_content_type() == "text/html":
        import re

        content = re.sub(r"<[^>]+>", "", content)
    return content.strip() or "(empty body)"


def _format_message(mail_from: str, rcpt_tos: list[str], msg) -> str:
    subject = msg.get("Subject", "(no subject)")
    from_header = msg.get("From", mail_from)
    to_header = msg.get("To", ", ".join(rcpt_tos))
    body = _extract_body(msg)

    return (
        f"\U0001F4E7 New SMTP message\n"
        f"From: {from_header}\n"
        f"To: {to_header}\n"
        f"Subject: {subject}\n"
        f"\n"
        f"{body}"
    )


async def _forward(loop, text: str, attachments: list[tuple[str, bytes]]) -> None:
    try:
        await loop.run_in_executor(None, telegram.send_message, text)
    except Exception:
        log.exception("Failed to forward message to Telegram")
        return

    for filename, content in attachments:
        try:
            await loop.run_in_executor(None, telegram.send_document, filename, content)
        except Exception:
            log.exception("Failed to forward attachment %r to Telegram", filename)


class TelegramForwardingHandler:
    async def handle_DATA(self, server, session, envelope):
        peer = session.peer[0] if session.peer else "unknown"
        loop = asyncio.get_event_loop()

        try:
            msg = message_from_bytes(envelope.content, policy=policy.default)
        except Exception:
            log.exception("Failed to parse message from %s", peer)
            return "250 Message accepted for delivery"

        log.info(
            "Received message from %s (mail_from=%s, rcpt_tos=%s, subject=%r)",
            peer,
            envelope.mail_from,
            envelope.rcpt_tos,
            msg.get("Subject", ""),
        )

        text = _format_message(envelope.mail_from, envelope.rcpt_tos, msg)

        attachments = []
        try:
            for part in msg.iter_attachments():
                filename = part.get_filename() or "attachment"
                content = part.get_content()
                if isinstance(content, str):
                    content = content.encode("utf-8", errors="replace")
                if len(content) > MAX_ATTACHMENT_SIZE:
                    log.warning("Skipping attachment %r: too large (%d bytes)", filename, len(content))
                    continue
                attachments.append((filename, content))
        except Exception:
            log.exception("Failed to read attachments from %s", peer)

        # Ack the SMTP transaction immediately and forward in the background:
        # devices with short SMTP timeouts shouldn't be left waiting on a
        # (possibly slow or unreachable) Telegram API call.
        asyncio.ensure_future(_forward(loop, text, attachments))

        return "250 Message accepted for delivery"
