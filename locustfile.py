"""
Scalable User Service — Production Load Test Suite
===================================================

Simulates real-world traffic patterns against the service.
Designed to run alongside Prometheus + Grafana for live metrics.

Usage:
    # 1. Seed test data (1000 users)
    uv run python setup_test_data.py

    # 2. Disable rate limiting for load testing
    export ENABLE_RATE_LIMITING=false

    # 3. Run the load test
    uv run locust -f locustfile.py --host http://localhost:8000

    # 4. Observe Prometheus metrics at http://localhost:9090
    #    Key queries:
    #      - RPS:       rate(http_requests_total[1m])
    #      - Latency:   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))
    #      - Cache:     rate(cache_operations_total{result="hit"}[1m])
    #      - In-flight: http_requests_in_progress

Environment Variables:
    LOAD_TEST_USERS_FILE  — Path to seeded credentials JSON (default: .loadtest_users.json)
    LOAD_TEST_MODE        — "steady" (default) | "spike" | "soak"
    LOAD_TEST_WAIT_MIN    — Min wait between tasks in seconds (default: 0.1)
    LOAD_TEST_WAIT_MAX    — Max wait between tasks in seconds (default: 1.0)
"""

import json
import os
import random
import threading
from pathlib import Path

from locust import HttpUser, between, constant, task
from locust.exception import StopUser

# --- Configuration ---
USERS_FILE = Path(os.getenv("LOAD_TEST_USERS_FILE", ".loadtest_users.json"))
LOAD_TEST_MODE = os.getenv("LOAD_TEST_MODE", "steady")
WAIT_MIN = float(os.getenv("LOAD_TEST_WAIT_MIN", "0.1"))
WAIT_MAX = float(os.getenv("LOAD_TEST_WAIT_MAX", "1.0"))


def load_credentials() -> list[dict]:
    """Load pre-seeded user credentials from the JSON file."""
    if not USERS_FILE.exists():
        raise RuntimeError(f"Credentials file not found: {USERS_FILE}. Run `uv run python setup_test_data.py` first.")
    with USERS_FILE.open() as f:
        users = json.load(f)
    if not users:
        raise RuntimeError("Credentials file is empty.")
    return users


# Only load credentials for modes that need them
_ALL_USERS: list[dict] = []
if LOAD_TEST_MODE in ("steady", "spike", "soak"):
    _ALL_USERS = load_credentials()

_credential_lock = threading.Lock()
_credential_index = 0


def acquire_credential() -> dict:
    """Thread-safe round-robin credential assignment."""
    global _credential_index
    if not _ALL_USERS:
        raise RuntimeError("No load test users available.")
    with _credential_lock:
        cred = _ALL_USERS[_credential_index % len(_ALL_USERS)]
        _credential_index += 1
        return cred


class AuthenticatedUser(HttpUser):
    """
    Simulates a real authenticated user session.

    Traffic distribution (realistic production mix):
      - 70% GET /me           (cache-heavy, the hottest endpoint)
      - 10% PATCH /me         (profile update, triggers cache invalidation)
      - 10% POST /refresh     (token rotation)
      -  5% POST /logout      (session end, blacklists both tokens)
      -  5% GET /health/ready (infra probe)
    """

    wait_time = between(WAIT_MIN, WAIT_MAX)
    weight = 10 if LOAD_TEST_MODE in ("steady", "soak") else 0

    def on_start(self) -> None:
        self.user_data = acquire_credential()
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None
        self._login()

    def _login(self) -> None:
        resp = self.client.post(
            "/api/v1/users/login",
            json={
                "email": self.user_data["email"],
                "password": self.user_data["password"],
            },
            name="/api/v1/users/login",
        )
        if resp.status_code != 200:
            raise StopUser(f"Login failed: {self.user_data['email']} -> {resp.status_code}")
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token_value = data["refresh_token"]
        self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

    @task(70)
    def get_profile(self) -> None:
        """GET /me — exercises Redis cache. Should be sub-10ms on cache hit."""
        self.client.get("/api/v1/users/me", name="/api/v1/users/me")

    @task(10)
    def update_profile(self) -> None:
        """PATCH /me — triggers cache invalidation + DB write."""
        self.client.patch(
            "/api/v1/users/me",
            json={"full_name": f"Load User {random.randint(1, 999999)}"},
            name="/api/v1/users/me [PATCH]",
        )

    @task(10)
    def refresh_session(self) -> None:
        """POST /refresh — rotates tokens, blacklists old refresh token."""
        resp = self.client.post(
            "/api/v1/users/refresh",
            json={"refresh_token": self.refresh_token_value},
            name="/api/v1/users/refresh",
        )
        if resp.status_code == 200:
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token_value = data["refresh_token"]
            self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})
        elif resp.status_code == 401:
            # Token was already rotated, re-login
            self._login()

    @task(5)
    def logout_and_relogin(self) -> None:
        """POST /logout + re-login — tests token blacklisting under load."""
        self.client.post(
            "/api/v1/users/logout",
            json={"refresh_token": self.refresh_token_value},
            name="/api/v1/users/logout",
        )
        self._login()

    @task(5)
    def health_check(self) -> None:
        """GET /health/ready — Kubernetes-style readiness probe."""
        self.client.get("/health/ready", name="/health/ready")


class SpikeUser(HttpUser):
    """
    Spike traffic simulation — aggressive, zero wait-time users
    hammering the /me endpoint to test cache resilience and
    connection pool behavior under extreme burst load.

    Use with: LOAD_TEST_MODE=spike
    """

    wait_time = constant(0)  # no wait — maximum pressure
    weight = 10 if LOAD_TEST_MODE == "spike" else 0

    def on_start(self) -> None:
        self.user_data = acquire_credential()
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None
        self._login()

    def _login(self) -> None:
        resp = self.client.post(
            "/api/v1/users/login",
            json={
                "email": self.user_data["email"],
                "password": self.user_data["password"],
            },
            name="/api/v1/users/login [spike]",
        )
        if resp.status_code != 200:
            raise StopUser(f"Spike login failed: {resp.status_code}")
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token_value = data["refresh_token"]
        self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

    @task(90)
    def hammer_profile(self) -> None:
        """Maximum pressure on GET /me — tests cache hit rate under flood."""
        self.client.get("/api/v1/users/me", name="/api/v1/users/me [spike]")

    @task(10)
    def hammer_login(self) -> None:
        """Re-login under spike — tests bcrypt throughput."""
        self._login()


class DbBenchUser(HttpUser):
    """
    DB-only benchmark — hits /bench/db which always queries Postgres.
    Measures raw uncached database capacity.

    Use with: LOAD_TEST_MODE=db
    """

    wait_time = constant(0)
    weight = 10 if LOAD_TEST_MODE == "db" else 0

    @task
    def hit_db(self) -> None:
        self.client.get("/bench/db", name="/bench/db")
