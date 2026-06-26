#!/bin/bash
# start.sh — Skrypt startowy betatp.io (Render.com + lokalne dev)
# Użycie: ./start.sh
set -e

echo "================================================="
echo "  betatp.io API — Starting up"
echo "================================================="

# PYTHONPATH domyślnie "." — działa i lokalnie i na Render
export PYTHONPATH="${PYTHONPATH:-.}"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"

echo "  Host:       $HOST"
echo "  Port:       $PORT"
echo "  Workers:    $WORKERS"
echo "  PYTHONPATH: $PYTHONPATH"
echo "-------------------------------------------------"

exec uvicorn api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
