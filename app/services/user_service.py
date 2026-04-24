from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import SignupRequest, UpdateUserRequest


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, id: int) -> User | None:
    result = await db.execute(select(User).where(id == User.id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, payload: SignupRequest) -> User:
    user = User(
        username=payload.username,
        email=str(payload.email),
        full_name=payload.full_name,
        password_hash=await hash_password(payload.password),
    )

    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(user)

    return user


async def check_user_password(user: User, password: str) -> bool:
    return await verify_password(password, user.password_hash)


async def update_user(
    db: AsyncSession,
    user: User,
    payload: UpdateUserRequest,
) -> User:
    if payload.username is not None:
        user.username = payload.username

    if payload.full_name is not None:
        user.full_name = payload.full_name

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(user)
    return user


async def update_user_password(db: AsyncSession, user: User, new_password: str) -> User:
    user.password_hash = await hash_password(new_password)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(user)
    return user


async def mark_user_verified(db: AsyncSession, user: User) -> User:
    user.is_verified = True

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(user)
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    await db.commit()
