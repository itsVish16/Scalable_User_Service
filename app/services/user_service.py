from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import SignupRequest

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, id: int) -> User | None:
    result= await db.execute(select(User).where(User.id == user.id))
    return result.scalar_one_or_none()
    

async def create_user(db: AsyncSession, payload: SignupRequest) -> User:
    user = User(
        username = payload.username,
        email=str(payload.email),
        full_name = payload.full_name,
        password_hash = hash_password(payload.password),
    )

    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    
    await db.refresh(user)

    return user

def check_user_password(user: User, password: str) -> bool:
    return verify_password(password, user.password_hash)


