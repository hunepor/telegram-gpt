#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Deploy the current committed local revision to a VPS over SSH.
The VPS does not need Git access. SSH access with permission to manage systemd is required.

Usage:
  SSH_TARGET=root@host [APP_DIR=/opt/telegram-gpt-deploy] \
    bash scripts/deploy-ssh.sh

Optional variables:
  SSH_PORT       SSH port (default: 22)
  SSH_KEY        Private key path passed to ssh (optional)
  APP_DIR        Release directory on the server (default: /opt/telegram-gpt-deploy)
  SERVICE_NAME   systemd service name (default: telegram-gpt)
  ENV_FILE       Environment file (default: /etc/telegram-gpt/bot.env)
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${SSH_TARGET:-}" ]]; then
  echo "SSH_TARGET is required (for example: root@203.0.113.10)." >&2
  usage >&2
  exit 2
fi

for command_name in git ssh tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name must be installed on the local machine." >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/telegram-gpt-deploy}"
SERVICE_NAME="${SERVICE_NAME:-telegram-gpt}"
ENV_FILE="${ENV_FILE:-/etc/telegram-gpt/bot.env}"
SSH_PORT="${SSH_PORT:-22}"

if [[ "$APP_DIR" != /* || ! "$APP_DIR" =~ ^/[A-Za-z0-9_./-]+$ || "/$APP_DIR/" == *"/../"* ]]; then
  echo "APP_DIR must be an absolute path without '..'." >&2
  exit 2
fi
if [[ ! "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]]; then
  echo "SERVICE_NAME contains unsupported characters." >&2
  exit 2
fi
if [[ "$ENV_FILE" != /* || ! "$ENV_FILE" =~ ^/[A-Za-z0-9_./-]+$ || "/$ENV_FILE/" == *"/../"* ]]; then
  echo "ENV_FILE must be an absolute path." >&2
  exit 2
fi

if ! git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Could not locate the local Git repository." >&2
  exit 2
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
  echo "The local worktree has uncommitted changes. Commit the intended release first." >&2
  exit 2
fi

COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
RELEASE_ID="${COMMIT:0:12}"
RELEASE_DIR="$APP_DIR/releases/$RELEASE_ID"
SSH_ARGS=(-p "$SSH_PORT")
if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_ARGS+=(-i "$SSH_KEY")
fi

printf -v REMOTE_PREPARE 'mkdir -p -- %q' "$RELEASE_DIR"
echo "Uploading committed release $RELEASE_ID to $SSH_TARGET:$RELEASE_DIR"
ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "$REMOTE_PREPARE"
printf -v REMOTE_EXTRACT 'tar -xf - -C %q' "$RELEASE_DIR"
git -C "$REPO_DIR" archive --format=tar HEAD | \
  ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "$REMOTE_EXTRACT"

printf -v REMOTE_DEPLOY 'bash -s -- %q %q %q %q %q' \
  "$APP_DIR" "$RELEASE_ID" "$SERVICE_NAME" "$ENV_FILE" "$COMMIT"
ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "$REMOTE_DEPLOY" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

app_dir="$1"
release_id="$2"
service_name="$3"
env_file="$4"
commit="$5"
release_dir="$app_dir/releases/$release_id"
current_link="$app_dir/current"
service_user="telegram-gpt"
service_group="telegram-gpt"
dropin_dir="/etc/systemd/system/$service_name.service.d"
dropin_file="$dropin_dir/90-local-release-deploy.conf"
state_dir="/var/lib/telegram-gpt"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "The SSH user must be root to install a systemd drop-in and restart the service." >&2
  exit 1
fi
if [[ ! -f "$env_file" ]]; then
  echo "Environment file not found: $env_file" >&2
  exit 1
fi
if [[ ! -f "$release_dir/bot.py" || ! -f "$release_dir/requirements.txt" ]]; then
  echo "Uploaded release is incomplete: $release_dir" >&2
  exit 1
fi
if ! id "$service_user" >/dev/null 2>&1; then
  echo "Service user '$service_user' does not exist. Install the VPS service first." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
  echo "python3 and systemd are required on the VPS." >&2
  exit 1
fi

mkdir -p "$state_dir" "$dropin_dir"
chown "$service_user:$service_group" "$state_dir"
chown -R "$service_user:$service_group" "$release_dir"
runuser -u "$service_user" -- python3 -m venv "$release_dir/.venv"
runuser -u "$service_user" -- \
  "$release_dir/.venv/bin/pip" install --disable-pip-version-check -r "$release_dir/requirements.txt"

if [[ -e "$dropin_file" ]] && ! grep -q 'Managed by scripts/deploy-ssh.sh' "$dropin_file"; then
  echo "Refusing to replace unmanaged systemd drop-in: $dropin_file" >&2
  exit 1
fi

previous_target=""
if [[ -L "$current_link" ]]; then
  previous_target="$(readlink "$current_link")"
elif [[ -e "$current_link" ]]; then
  echo "Expected $current_link to be a symlink; refusing to replace it." >&2
  exit 1
fi
had_dropin=0
previous_dropin=""
if [[ -f "$dropin_file" ]]; then
  had_dropin=1
  previous_dropin="$(mktemp)"
  cp -p "$dropin_file" "$previous_dropin"
fi

rollback() {
  result=$?
  trap - ERR
  if [[ -n "$previous_target" ]]; then
    ln -sfn "$previous_target" "$current_link.rollback"
    mv -Tf "$current_link.rollback" "$current_link"
  else
    rm -f "$current_link"
  fi
  if (( had_dropin )); then
    cp -p "$previous_dropin" "$dropin_file"
    rm -f "$previous_dropin"
  else
    rm -f "$dropin_file"
  fi
  systemctl daemon-reload || true
  systemctl restart "$service_name" || true
  echo "Deployment failed; restored the previous release." >&2
  exit "$result"
}
trap rollback ERR

cat > "$dropin_file" <<DROPIN
# Managed by scripts/deploy-ssh.sh
[Service]
WorkingDirectory=$current_link
EnvironmentFile=
EnvironmentFile=$env_file
Environment=STATE_DB_PATH=$state_dir/bot.db
StateDirectory=telegram-gpt
StateDirectoryMode=0700
ExecStart=
ExecStart=$current_link/.venv/bin/python $current_link/bot.py
DROPIN

ln -s "$release_dir" "$current_link.next"
mv -Tf "$current_link.next" "$current_link"
systemctl daemon-reload
systemctl restart "$service_name"
systemctl is-active --quiet "$service_name"

trap - ERR
rm -f "$previous_dropin"
echo "Deployment complete: $commit; $service_name is active."
REMOTE_SCRIPT
