#!/usr/bin/env sh
set -eu

APP_DIR="/opt/telegram-gpt"
SERVICE_USER="telegram-gpt"
ENV_DIR="/etc/telegram-gpt"
ENV_FILE="$ENV_DIR/bot.env"
SERVICE_FILE="/etc/systemd/system/telegram-gpt.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root: sudo bash scripts/vps-install.sh" >&2
  exit 1
fi

if [ ! -f "$APP_DIR/requirements.txt" ] || [ ! -f "$APP_DIR/deploy/telegram-gpt.service" ]; then
  echo "Repository not found in $APP_DIR." >&2
  echo "Clone it there first, as shown in README.md." >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu and Debian systems with apt-get." >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  echo "Python 3.10 or newer is required." >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  runuser -u "$SERVICE_USER" -- python3 -m venv "$APP_DIR/.venv"
fi

runuser -u "$SERVICE_USER" -- \
  "$APP_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements.txt"

install -d -m 700 -o root -g root "$ENV_DIR"
if [ ! -f "$ENV_FILE" ]; then
  install -m 600 -o root -g root "$APP_DIR/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example."
fi

install -m 644 "$APP_DIR/deploy/telegram-gpt.service" "$SERVICE_FILE"
systemctl daemon-reload

echo
echo "Installation complete."
echo "1. Edit tokens: sudo nano $ENV_FILE"
echo "2. Start bot:  sudo systemctl enable --now telegram-gpt"
echo "3. View logs:  sudo journalctl -u telegram-gpt -f"
