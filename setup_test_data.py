import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.security import hash_password

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://userservice:userservice@localhost:5432/userservice",
)
LOAD_TEST_USER_COUNT = int(os.getenv("LOAD_TEST_USER_COUNT", "5000"))
LOAD_TEST_PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "LoadTestPass123")
LOAD_TEST_BATCH_SIZE = int(os.getenv("LOAD_TEST_BATCH_SIZE", "250"))
OUTPUT_FILE = Path(os.getenv("LOAD_TEST_USERS_FILE", ".loadtest_users.json"))


async def setup() -> None:
    print(f"Connecting to database: {DATABASE_URL}")
    print(f"Preparing {LOAD_TEST_USER_COUNT} verified users for load testing")

    engine = create_async_engine(DATABASE_URL)
    password_hash = await hash_password(LOAD_TEST_PASSWORD)
    users = []

    for index in range(1, LOAD_TEST_USER_COUNT + 1):
        users.append(
            {
                "email": f"loadtest_{index}@example.com",
                "username": f"loadtestuser_{index}",
                "full_name": f"Load Test User {index}",
                "password_hash": password_hash,
                "password": LOAD_TEST_PASSWORD,
            }
        )

    upsert_query = text(
        """
        INSERT INTO users (email, username, full_name, password_hash, is_verified, created_at, updated_at)
        VALUES (:email, :username, :full_name, :password_hash, true, NOW(), NOW())
        ON CONFLICT (email) DO UPDATE SET
            username = EXCLUDED.username,
            full_name = EXCLUDED.full_name,
            password_hash = EXCLUDED.password_hash,
            is_verified = true,
            updated_at = NOW()
        """
    )

    try:
        async with engine.begin() as connection:
            for start in range(0, len(users), LOAD_TEST_BATCH_SIZE):
                batch = users[start : start + LOAD_TEST_BATCH_SIZE]
                await connection.execute(upsert_query, batch)
                print(f"Seeded batch {start + 1}-{start + len(batch)}")

        load_test_credentials = [
            {
                "email": user["email"],
                "username": user["username"],
                "password": user["password"],
            }
            for user in users
        ]
        OUTPUT_FILE.write_text(json.dumps(load_test_credentials, indent=2))
        print(f"Wrote credentials to {OUTPUT_FILE}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(setup())
