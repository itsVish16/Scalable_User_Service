# Scalable User Service

FastAPI user service with JWT auth, Redis-backed caching, Postgres persistence, Prometheus metrics, and a Dockerized local stack for development and load testing.

## Local Stack

Start everything with Docker:

```bash
docker compose up --build
```

This now brings up:

- API on [http://localhost:8000](http://localhost:8000)
- Postgres on `localhost:5432`
- Redis on `localhost:6379`
- Prometheus on [http://localhost:9090](http://localhost:9090)
- Grafana on [http://localhost:3000](http://localhost:3000)

The API container runs `alembic upgrade head` automatically before starting Uvicorn.

## Environment

Create your local env file:

```bash
cp .env.example .env
```

Important controls now exposed through `.env`:

- `ENABLE_RATE_LIMITING=true|false`
- `RATE_LIMIT_SIGNUP`, `RATE_LIMIT_LOGIN`, `RATE_LIMIT_REFRESH`
- `RATE_LIMIT_FORGOT_PASSWORD`, `RATE_LIMIT_RESET_PASSWORD`
- `RATE_LIMIT_VERIFY_EMAIL`, `RATE_LIMIT_RESEND_VERIFICATION`
- `MAX_LOGIN_ATTEMPTS`
- `LOGIN_LOCKOUT_SECONDS`
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`
- `REDIS_MAX_CONNECTIONS`
- `CORS_ALLOWED_ORIGINS`

## Current Auth Flow

- Signup creates the user as unverified.
- Verification OTP and reset OTP are stored in Redis.
- Email sending is disconnected for now.
- In `DEBUG=true`, OTP values are returned in success messages for easy testing.
- In non-debug mode, endpoints return generic success messages.

## Monitoring Endpoints

- App metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Prometheus UI: [http://localhost:9090](http://localhost:9090)
- Grafana UI: [http://localhost:3000](http://localhost:3000)

Grafana is pre-provisioned with Prometheus as the default datasource.

## Tests

```bash
uv run pytest
```

## Load Testing

Seed verified load-test users:

```bash
LOAD_TEST_USER_COUNT=1000 uv run setup_test_data.py
```

Keep `LOAD_TEST_USER_COUNT` at least as large as your planned concurrent Locust users so each simulated user gets a unique identity.

Run steady-state traffic:

```bash
LOAD_TEST_MODE=steady uv run locust --headless -u 300 -r 30 --run-time 5m --host=http://localhost:8000
```

Run the rate-limit probe separately:

```bash
LOAD_TEST_MODE=rate-limit uv run locust --headless -u 20 -r 5 --run-time 2m --host=http://localhost:8000
```

The full plan is in [docs/load-testing.md](/Users/vishal/Desktop/WorkSpace2/Scalable_User_Service/docs/load-testing.md).
