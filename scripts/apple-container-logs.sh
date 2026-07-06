#!/usr/bin/env sh
set -eu

CONTAINER_NAME="${CONTAINER_NAME:-telegram-gpt}"

container logs --follow "$CONTAINER_NAME"
