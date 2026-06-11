FROM python:3.13-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/
COPY docker/ ./docker/

RUN chmod +x /app/docker/start.sh

RUN adduser --disabled-password --no-create-home --gecos "" appuser
USER appuser

EXPOSE 8000

CMD ["/app/docker/start.sh"]
