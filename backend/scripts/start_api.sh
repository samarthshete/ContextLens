#!/usr/bin/env sh
# API startup for hosted (e.g. Render) deploys: run DB migrations, then serve.
# Free instances don't support preDeployCommand, so migrations run here.
# CREATE EXTENSION vector runs inside Alembic (see render.yaml notes).
set -eu
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
