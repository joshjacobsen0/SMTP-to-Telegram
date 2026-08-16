# SMTP to Telegram

A small local server that pretends to be an SMTP mail server, so that LAN
devices (cameras, NAS boxes, UPS units, routers, etc.) which can only send
plain/unauthenticated SMTP "status notification" emails can keep working
even though your real mail provider no longer accepts plain SMTP.

Every message it receives is parsed and forwarded to you as a Telegram
message. It does not deliver mail anywhere else, does not send replies, and
does not enforce real SMTP authentication — any device that can reach it on
your network can send through it (see **Security notes** below).

## How it works

- Listens for SMTP connections (`aiosmtpd`), accepting mail with or without
  `AUTH` (any username/password is accepted; SMTP AUTH is opt-in per client).
- Parses each message (subject, from, to, plain-text body, attachments).
- Forwards the text as a Telegram message via the Bot API, and forwards any
  attachments (e.g. camera snapshots) as Telegram documents.
- Acknowledges the SMTP transaction immediately and forwards to Telegram in
  the background, so a slow/unreachable Telegram API never makes a sending
  device time out.

## Setup

> **Linux users:** if you're deploying on Debian/Ubuntu (e.g. a Proxmox LXC
> container), you can skip steps 2–4 below — the included
> [`install.sh`](install.sh) automates dependency installation, `.env`
> configuration, and running it as a systemd service in one step. See
> [Running it continuously → Linux](#running-it-continuously) for details.
> You'll still need step 1 first either way.

### 1. Create a Telegram bot and get your chat ID

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
   and follow the prompts. You'll get a bot token like
   `123456789:AAH...`.
2. Send any message to your new bot (search for it by the username you gave
   it, and press Start).
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   and find `"chat":{"id":...}` in the response — that number is your
   `TELEGRAM_CHAT_ID`.

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Adjust
`SMTP_HOST` / `SMTP_PORT` if needed (default: blank host on port `2525`,
i.e. reachable from any device on your LAN, on a port that doesn't need
admin privileges). Leave `SMTP_HOST` blank rather than `0.0.0.0` — on
Windows, `aiosmtpd`'s startup check fails if it's set literally to
`0.0.0.0` (the app also auto-corrects this for you if you do set it).

### 4. Run

```bash
python main.py
```

### 5. Point your devices at it

In each device's SMTP/email-notification settings, set:

- **Server**: the IP address of the machine running this app
- **Port**: `2525` (or whatever you set `SMTP_PORT` to)
- **Encryption**: none / plain (no TLS/SSL, no STARTTLS)
- **Username/password**: anything, or leave blank — it's not checked

If your device insists on port `25` or `587`, set `SMTP_PORT` accordingly.
Ports below 1024 typically need the app to run elevated (Administrator on
Windows, root on Linux/macOS).

## Running it continuously

This app has no built-in daemonization — pick whichever fits your platform:

- **Windows**: run it as a scheduled task at logon (Task Scheduler), or wrap
  it as a service with [NSSM](https://nssm.cc/).
- **Linux**: run it under `systemd` (a simple `.service` unit calling
  `python3 main.py` with `Restart=on-failure`) or a process manager like
  `pm2`/`supervisord`. On Debian/Ubuntu (e.g. a Proxmox LXC container), the
  included `install.sh` automates this: it installs dependencies, prompts
  for your bot token / chat ID / listener IP (or reads them from the
  environment for non-interactive/scripted installs), and installs +
  enables a systemd service. Safe to re-run — it keeps your existing `.env`
  values as defaults.

  ```bash
  sudo ./install.sh
  # or, non-interactively:
  sudo TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy SMTP_HOST=192.168.1.50 ./install.sh
  ```
- **macOS**: run it under `launchd` so it starts at boot and restarts if it
  crashes. Create `/Library/LaunchDaemons/com.local.smtp-to-telegram.plist`
  (adjust the paths to match where you put the project and which `python3`
  you want to use — a Homebrew install is recommended, see
  **Troubleshooting** below):

  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
      <key>Label</key>
      <string>com.local.smtp-to-telegram</string>
      <key>ProgramArguments</key>
      <array>
          <string>/opt/homebrew/bin/python3</string>
          <string>/path/to/SMTP-to-Telegram/main.py</string>
      </array>
      <key>WorkingDirectory</key>
      <string>/path/to/SMTP-to-Telegram</string>
      <key>RunAtLoad</key>
      <true/>
      <key>KeepAlive</key>
      <true/>
      <key>StandardOutPath</key>
      <string>/path/to/SMTP-to-Telegram/stdout.log</string>
      <key>StandardErrorPath</key>
      <string>/path/to/SMTP-to-Telegram/stderr.log</string>
  </dict>
  </plist>
  ```

  Then load it:

  ```bash
  sudo launchctl load /Library/LaunchDaemons/com.local.smtp-to-telegram.plist
  ```

  A `LaunchDaemon` (under `/Library/LaunchDaemons`, loaded with `sudo`) runs
  at boot regardless of whether anyone is logged in — useful for a headless
  Mac mini. It also runs as root by default, which lets you bind directly to
  port `25`/`587` if you want; add a `<key>UserName</key>` entry if you'd
  rather it run as your normal user (then stick to a port above 1024).

## Troubleshooting

- **`CERTIFICATE_VERIFY_FAILED` / `self-signed certificate in certificate
  chain` when forwarding to Telegram**: Python couldn't validate
  `api.telegram.org`'s certificate against its trusted root store. This is
  not usually a real security problem, just a missing/stale CA bundle:
  - *Windows*: Windows fetches root certificates on demand the first time an
    OS-native app needs them, but Python's bundled OpenSSL only reads
    whatever's already cached — it doesn't trigger the fetch itself. Opening
    any HTTPS site in Edge (or anything else that uses Windows' own crypto
    APIs) once is usually enough to populate the cache, after which Python
    works too.
  - *macOS*: if Python was installed from python.org, it ships without a
    configured CA bundle until you run
    `/Applications/Python 3.x/Install Certificates.command`. Installing
    Python via Homebrew (`brew install python3`) avoids this, since it links
    against the system's trust store from the start.

## Security notes

- This server does **not** enforce authentication or encryption on purpose,
  to stay compatible with simple devices. Anyone who can reach the listening
  port on your network can send a message through it to your Telegram chat.
- Keep `SMTP_HOST` bound to your LAN only (don't port-forward it to the
  internet), and set `SMTP_HOST=127.0.0.1` if every sending device is on the
  same machine.
- `.env` contains your bot token — it's already excluded via `.gitignore`.
