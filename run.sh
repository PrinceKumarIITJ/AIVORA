#!/bin/sh
set -eu
cd "$(dirname "$0")"
test -d .venv || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
export PYTHONPATH="$PWD/src"
printf 'AIVORA: http://127.0.0.1:8090\n'
exec .venv/bin/python -m uvicorn aivora.main:app --host 127.0.0.1 --port 8090
