import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base, get_db
from app.db.redis import get_redis
from app.main import app

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)

    async def ping(self):
        return True


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


async def override_get_db():
    async with TestSession() as session:
        yield session


@pytest.fixture(autouse=True)
def override_dependencies():
    from app.core.rate_limit import limiter
    from app.tasks.celery_app import celery_app

    limiter.enabled = False
    original_eager_prop = celery_app.conf.task_eager_propagates
    celery_app.conf.task_eager_propagates = False

    fake = FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake
    yield fake
    app.dependency_overrides.clear()
    limiter.enabled = True
    celery_app.conf.task_eager_propagates = original_eager_prop


@pytest.fixture
def fake_redis(override_dependencies):
    return override_dependencies


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def unique_id():
    return uuid.uuid4().hex[:8]


async def signup_user(client, username_prefix="testuser", verified=False, fake_redis=None):
    uid = unique_id()
    payload = {
        "username": f"{username_prefix}_{uid}",
        "email": f"{username_prefix}_{uid}@example.com",
        "full_name": "Test User",
        "password": "Password123",
    }

    response = await client.post("/api/v1/users/signup", json=payload)
    assert response.status_code == 201

    if verified and fake_redis is not None:
        msg = response.json()["message"]
        otp = msg.split("Verification OTP: ", 1)[1]
        verify_resp = await client.post(
            "/api/v1/users/verify-email",
            json={"email": payload["email"], "token": otp},
        )
        assert verify_resp.status_code == 200

    return payload, response


async def login_user(client, email, password):
    response = await client.post(
        "/api/v1/users/login",
        json={"email": email, "password": password},
    )
    return response
