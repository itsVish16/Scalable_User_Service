from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Conditionally apply pooling settings (Postgres only)
engine_kwargs = {}
if settings.database_url.startswith("postgresql"):
    engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 30,
            "pool_timeout": 30,
        }
    )

engine = create_async_engine(settings.database_url, **engine_kwargs)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
