#!/usr/bin/env sh
set -eu

IMAGE_NAME="${IMAGE_NAME:-telegram-gpt-bot:local}"

command -v container >/dev/null 2>&1 || {
  echo "Apple container CLI is not installed or not in PATH." >&2
  exit 1
}

container build -t "$IMAGE_NAME" .
