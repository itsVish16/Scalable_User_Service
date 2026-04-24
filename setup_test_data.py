import asyncio

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# We need to import security to generate the token
from app.core.security import create_access_token, hash_password

load_dotenv()

# We explicitly connect to the local Docker Postgres container
DATABASE_URL = "postgresql+asyncpg://userservice:userservice@localhost:5432/userservice"


async def setup():
    print(f"Connecting to database: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)

    # Check if we can connect
    try:
        async with engine.begin() as conn:
            # Create a test user directly in SQL to bypass the /signup endpoint and avoid sending emails
            password_hash = await hash_password("LoadTestPass123")

            # Use raw SQL to insert so we don't need the full ORM setup
            query = text("""
                INSERT INTO users (email, username, full_name, password_hash, is_verified, created_at, updated_at)
                VALUES (:email, :username, :full_name, :password, true, NOW(), NOW())
                ON CONFLICT (email) DO UPDATE SET is_verified = true
                RETURNING id;
            """)

            result = await conn.execute(
                query,
                {
                    "email": "loadtest@example.com",
                    "username": "loadtestuser",
                    "full_name": "Load Test User",
                    "password": password_hash,
                },
            )

            user_id = result.scalar()
            print(f"Test user created/found with ID: {user_id}")

            # Generate token
            token = create_access_token(str(user_id))
            print("\n" + "=" * 50)
            print("ACCESS_TOKEN FOR LOAD TEST:")
            print(token)
            print("=" * 50 + "\n")

            # Write token to a file so Locust can read it automatically
            with open(".loadtest_token", "w") as f:
                f.write(token)

    except Exception as e:
        print(f"Error setting up test data: {e}")
        print("Make sure Docker is running and the database is accessible!")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(setup())
