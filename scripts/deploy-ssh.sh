#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Deploy the current local Git branch to an installed telegram-gpt VPS over SSH.

Usage:
  SSH_TARGET=user@host [APP_DIR=/opt/telegram-gpt] [SERVICE_NAME=telegram-gpt] \
    bash scripts/deploy-ssh.sh

Optional variables:
  SSH_PORT       SSH port (default: 22)
  SSH_KEY        Private key path passed to ssh (optional)
  APP_DIR        Repository directory on the server (default: /opt/telegram-gpt)
  SERVICE_NAME   systemd service name (default: telegram-gpt)
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${SSH_TARGET:-}" ]]; then
  echo "SSH_TARGET is required (for example: deploy@203.0.113.10)." >&2
  usage >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1 || ! command -v ssh >/dev/null 2>&1; then
  echo "git and ssh must be installed on the local machine." >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/telegram-gpt}"
SERVICE_NAME="${SERVICE_NAME:-telegram-gpt}"
SSH_PORT="${SSH_PORT:-22}"

if ! git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Could not locate the local Git repository." >&2
  exit 2
fi

BRANCH="$(git -C "$REPO_DIR" branch --show-current)"
if [[ -z "$BRANCH" ]]; then
  echo "The local repository is in detached HEAD state; check out a branch first." >&2
  exit 2
fi

if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
  echo "The local worktree has uncommitted changes. Commit and push the intended changes before deploying." >&2
  exit 2
fi

if [[ -z "$(git -C "$REPO_DIR" ls-remote --heads origin "$BRANCH")" ]]; then
  echo "Branch '$BRANCH' was not found on origin. Push it before deploying." >&2
  exit 2
fi

SSH_ARGS=(-p "$SSH_PORT")
if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_ARGS+=(-i "$SSH_KEY")
fi

echo "Deploying origin/$BRANCH to $SSH_TARGET:$APP_DIR"
ssh "${SSH_ARGS[@]}" "$SSH_TARGET" bash -s -- "$APP_DIR" "$SERVICE_NAME" "$BRANCH" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

app_dir="$1"
service_name="$2"
branch="$3"

if [[ ! -d "$app_dir/.git" ]]; then
  echo "Git repository not found at $app_dir." >&2
  exit 1
fi
if [[ ! -x "$app_dir/.venv/bin/pip" ]]; then
  echo "Python environment not found at $app_dir/.venv. Install the VPS service first." >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to restart the systemd service." >&2
  exit 1
fi

cd "$app_dir"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Server worktree has local changes; refusing to overwrite them." >&2
  exit 1
fi

git fetch --prune origin
git checkout "$branch"
git pull --ff-only origin "$branch"
.venv/bin/pip install --disable-pip-version-check -r requirements.txt
sudo systemctl restart "$service_name"
sudo systemctl is-active --quiet "$service_name"
echo "Deployment complete: $(git rev-parse --short HEAD); $service_name is active."
REMOTE_SCRIPT
