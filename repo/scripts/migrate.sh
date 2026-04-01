#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/migrate.sh              — upgrade to head
#   ./scripts/migrate.sh downgrade -1 — roll back one revision
#   ./scripts/migrate.sh revision "message" — create new migration

ACTION="${1:-upgrade}"

case "$ACTION" in
  upgrade)
    flask db upgrade "${2:-head}"
    ;;
  downgrade)
    flask db downgrade "${2:--1}"
    ;;
  revision)
    flask db revision --autogenerate -m "${2:-auto}"
    ;;
  *)
    echo "Usage: migrate.sh [upgrade|downgrade|revision] [arg]"
    exit 1
    ;;
esac
