# Load Testing Plan

## Goals

- Exercise the steady-state auth workload with realistic verified users.
- Separate throughput testing from rate-limit and lockout correctness checks.
- Observe cache hit behavior, request latency, and dependency health through Prometheus and Grafana.

## 1. Seed Verified Users

```bash
LOAD_TEST_USER_COUNT=1000 uv run setup_test_data.py
```

This creates verified users directly in Postgres and writes reusable credentials to `.loadtest_users.json`.
Set `LOAD_TEST_USER_COUNT` to at least the same number as your planned concurrent Locust users.

## 2. Steady-State Traffic

```bash
LOAD_TEST_MODE=steady uv run locust --headless -u 300 -r 30 --run-time 5m --host=http://localhost:8000
```

Traffic mix:

- `GET /api/v1/users/me` to exercise the Redis cache-first profile path
- `POST /api/v1/users/refresh` to keep JWT rotation under load
- `PATCH /api/v1/users/me` to create cache invalidations
- `GET /health/ready` to reflect platform probe traffic

## 3. Warm Cache vs Cold Cache

Warm cache:

```bash
LOAD_TEST_MODE=steady uv run locust --headless -u 100 -r 20 --run-time 2m --host=http://localhost:8000
```

Cold cache:

```bash
docker compose exec redis redis-cli FLUSHALL
LOAD_TEST_MODE=steady uv run locust --headless -u 100 -r 20 --run-time 2m --host=http://localhost:8000
```

## 4. Rate-Limit Probe

```bash
LOAD_TEST_MODE=rate-limit uv run locust --headless -u 20 -r 5 --run-time 2m --host=http://localhost:8000
```

This mode repeatedly hits the login endpoint with bad credentials so we can verify `401` to `429` transitions separately from the main throughput run.

## 5. What to Watch

- API metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Prometheus: [http://localhost:9090](http://localhost:9090)
- Grafana: [http://localhost:3000](http://localhost:3000)

Key signals:

- `http_requests_total`
- `http_request_duration_seconds`
- Postgres readiness under concurrent refresh and patch traffic
- Redis readiness and cache-backed `/me` latency
- `401` and `429` counts during the rate-limit probe
