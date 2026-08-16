#!/usr/bin/env bash
# Installs dependencies, writes .env (interactively or from the environment),
# and sets up a systemd service so the forwarder starts on boot.
# Safe to re-run: it updates the venv, keeps existing .env values as
# defaults, and reinstalls/restarts the service.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
VENV_DIR="$SCRIPT_DIR/.venv"
SERVICE_NAME="smtp-to-telegram"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log()  { printf '==> %s\n' "$*" >&2; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "This installs system packages and a systemd service, so it needs root (try: sudo ./install.sh)"

is_interactive() { [ -t 0 ]; }

# get_default KEY FALLBACK
# Looks up KEY in an existing .env first (so re-running the script keeps
# your current settings as defaults), then .env.example, then FALLBACK.
get_default() {
    local key="$1" fallback="$2" val=""
    if [ -f "$ENV_FILE" ]; then
        val="$(grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2-)"
    fi
    if [ -z "$val" ] && [ -f "$ENV_EXAMPLE" ]; then
        val="$(grep -E "^${key}=" "$ENV_EXAMPLE" | head -n1 | cut -d= -f2-)"
    fi
    [ -n "$val" ] && printf '%s' "$val" || printf '%s' "$fallback"
}

# prompt_value VAR_NAME PROMPT_TEXT DEFAULT REQUIRED SECRET
# Precedence: an already-exported env var wins (for non-interactive/scripted
# installs), then an interactive prompt, then DEFAULT if not interactive.
prompt_value() {
    local var_name="$1" prompt_text="$2" default_value="$3" required="$4" secret="$5"
    local preset="${!var_name:-}"

    if [ -n "$preset" ]; then
        log "Using \$$var_name from the environment"
        printf '%s' "$preset"
        return
    fi

    if ! is_interactive; then
        if [ -z "$default_value" ] && [ "$required" = "yes" ]; then
            warn "$var_name not set and not running interactively -- leaving blank, edit $ENV_FILE before starting the service"
        fi
        printf '%s' "$default_value"
        return
    fi

    local hint="$default_value"
    if [ "$secret" = "yes" ] && [ -n "$default_value" ]; then
        hint="leave blank to keep the current one"
    elif [ -z "$default_value" ]; then
        hint="none"
    fi

    while true; do
        local input=""
        if [ "$secret" = "yes" ]; then
            read -r -s -p "$prompt_text [$hint]: " input
            printf '\n' >&2
        else
            read -r -p "$prompt_text [$hint]: " input
        fi

        [ -z "$input" ] && input="$default_value"

        if [ -z "$input" ] && [ "$required" = "yes" ]; then
            printf 'This value is required.\n' >&2
            continue
        fi

        printf '%s' "$input"
        return
    done
}

log "Installing system packages"
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv ca-certificates >/dev/null
else
    warn "apt-get not found -- skipping system package install. Make sure python3 and the venv module are available."
fi

log "Setting up the virtual environment"
[ -d "$VENV_DIR" ] || python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

log "Configuring .env"
TELEGRAM_BOT_TOKEN="$(prompt_value TELEGRAM_BOT_TOKEN "Telegram bot token" "$(get_default TELEGRAM_BOT_TOKEN "")" yes yes)"
TELEGRAM_CHAT_ID="$(prompt_value TELEGRAM_CHAT_ID "Telegram chat ID" "$(get_default TELEGRAM_CHAT_ID "")" yes no)"
SMTP_HOST="$(prompt_value SMTP_HOST "Listener IP/interface (blank = all interfaces)" "$(get_default SMTP_HOST "")" no no)"
SMTP_PORT="$(get_default SMTP_PORT "2525")"
MAX_MESSAGE_SIZE="$(get_default MAX_MESSAGE_SIZE "10485760")"

cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
MAX_MESSAGE_SIZE=${MAX_MESSAGE_SIZE}
EOF
chmod 600 "$ENV_FILE"

if command -v systemctl >/dev/null 2>&1; then
    log "Installing the systemd service"

    service_user_line=""
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        service_user_line="User=${SUDO_USER}"
    fi

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=SMTP to Telegram forwarder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python ${SCRIPT_DIR}/main.py
Restart=on-failure
RestartSec=5
${service_user_line}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now "$SERVICE_NAME"

    log "Done. Service '$SERVICE_NAME' is enabled and running."
    log "Listening on: ${SMTP_HOST:-<all interfaces>}:${SMTP_PORT}"
    log "Check status with: systemctl status $SERVICE_NAME"
    log "Follow logs with:  journalctl -u $SERVICE_NAME -f"
else
    warn "systemctl not found -- skipping service install. Run 'python3 main.py' manually (or set up your own service) using $VENV_DIR/bin/python."
fi
