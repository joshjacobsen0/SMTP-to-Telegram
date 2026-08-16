"""Local SMTP server that forwards every received message to Telegram.

Intended for LAN devices (cameras, NAS, UPS, routers, etc.) that can only
send plain, unauthenticated SMTP "status notification" emails but whose
real mail provider no longer accepts unauthenticated/plaintext connections.
"""

import logging
import signal
import time

import config
from aiosmtpd.controller import Controller
from smtp_handler import TelegramForwardingHandler, accept_all_auth

log = logging.getLogger("main")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    config.validate()

    controller = Controller(
        TelegramForwardingHandler(),
        hostname=config.SMTP_HOST,
        port=config.SMTP_PORT,
        data_size_limit=config.MAX_MESSAGE_SIZE,
        auth_required=False,
        auth_require_tls=False,
        auth_callback=accept_all_auth,
        decode_data=False,
    )

    controller.start()
    log.info("SMTP-to-Telegram forwarder listening on %s:%s", config.SMTP_HOST, config.SMTP_PORT)
    log.info("Point your devices' SMTP settings at this host/port with no TLS and any (or no) credentials.")

    stop = False

    def _handle_stop(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    try:
        signal.signal(signal.SIGTERM, _handle_stop)
    except (AttributeError, ValueError):
        pass  # SIGTERM not available on this platform

    try:
        while not stop:
            time.sleep(0.5)
    finally:
        log.info("Shutting down")
        controller.stop()


if __name__ == "__main__":
    main()
