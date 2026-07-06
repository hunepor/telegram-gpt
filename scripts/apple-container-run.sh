#!/usr/bin/env sh
set -eu

IMAGE_NAME="${IMAGE_NAME:-telegram-gpt-bot:local}"
CONTAINER_NAME="${CONTAINER_NAME:-telegram-gpt}"
ENV_FILE="${ENV_FILE:-.env}"

command -v container >/dev/null 2>&1 || {
  echo "Apple container CLI is not installed or not in PATH." >&2
  exit 1
}

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Create it from .env.example and fill in your tokens." >&2
  exit 1
fi

container run \
  -d \
  --name "$CONTAINER_NAME" \
  --env-file "$ENV_FILE" \
  "$IMAGE_NAME"
