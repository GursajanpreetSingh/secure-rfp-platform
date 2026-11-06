#!/usr/bin/env bash
# Usage: bash scripts/dev.sh <command>
set -e

case "$1" in
  lint)
    uv run ruff check .
    uv run ruff format --check .
    ;;
  fmt)
    uv run ruff check --fix .
    uv run ruff format .
    ;;
  test)
    uv run pytest
    ;;
  check)
    uv run ruff check .
    uv run ruff format --check .
    uv run pytest
    ;;
  *)
    echo "Usage: bash scripts/dev.sh {lint|fmt|test|check}"
    exit 1
    ;;
esac
