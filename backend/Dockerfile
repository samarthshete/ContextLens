FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
COPY scripts ./scripts
COPY tests ./tests

RUN chmod +x scripts/rq_worker.sh

# Install package + all [project] dependencies from pyproject.toml (includes ``openai``).
# Also install [dev] extras so ``pytest`` can run inside the container.
RUN pip install --no-cache-dir ".[dev]" \
    && python -c "import openai; import anthropic; import pytest; print('deps ok: openai + anthropic + pytest')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]