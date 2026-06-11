#!/bin/sh
set -e

alembic upgrade head

WORKERS=${UVICORN_WORKERS:-1}
LOOP=${UVICORN_LOOP:-auto}

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS" --loop "$LOOP"

