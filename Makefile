.PHONY: dev test lint format migrate worker

dev:
	uvicorn app.main:app --reload

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

migrate:
	alembic upgrade head

worker:
	celery -A app.tasks.celery_app.celery_app worker --loglevel=info

up:
	docker compose up --build -d

down:
	docker compose down
