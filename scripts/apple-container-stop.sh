#!/usr/bin/env sh
set -eu

CONTAINER_NAME="${CONTAINER_NAME:-telegram-gpt}"

container stop "$CONTAINER_NAME"
container delete "$CONTAINER_NAME"
