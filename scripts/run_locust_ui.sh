#!/usr/bin/env bash
set -euo pipefail

HOST="${LOCUST_HOST:-http://127.0.0.1:8000}"
WEB_HOST="${LOCUST_WEB_HOST:-127.0.0.1}"
WEB_PORT="${LOCUST_WEB_PORT:-8089}"

./venv/Scripts/python.exe -m locust \
  -f tests/locust/locustfile.py \
  --host "$HOST" \
  --web-host "$WEB_HOST" \
  --web-port "$WEB_PORT"
