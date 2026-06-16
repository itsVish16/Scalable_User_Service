FROM python:3.13-slim as builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy project files
COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY docker docker

RUN uv sync --frozen --no-dev

FROM python:3.13-slim as runtime
WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application files
COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY docker docker

RUN chmod +x docker/start.sh

CMD ["/app/docker/start.sh"]
