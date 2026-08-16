"""Loads configuration from environment variables, with optional .env support."""

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(Path(__file__).with_name(".env"))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
if SMTP_HOST == "0.0.0.0":
    # aiosmtpd's startup self-check connects back to this hostname; on
    # Windows, connecting a socket to 0.0.0.0 fails (WinError 10049), unlike
    # Linux where it's treated as localhost. "" binds all interfaces the
    # same way but aiosmtpd substitutes localhost for the self-check.
    SMTP_HOST = ""
SMTP_PORT = int(os.environ.get("SMTP_PORT", "2525"))
MAX_MESSAGE_SIZE = int(os.environ.get("MAX_MESSAGE_SIZE", str(10 * 1024 * 1024)))


def validate() -> None:
    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required configuration: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill in the values, "
            "or set them as environment variables."
        )
