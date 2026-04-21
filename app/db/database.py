from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size = 10,
    max_overflow = 30,
    pool_timeout = 30,
)

SessioLocal = async_sessionmaker(engine, expire_on_commit = False)

class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessioLocal() as session:
        yield session