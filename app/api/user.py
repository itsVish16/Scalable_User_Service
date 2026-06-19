import hmac
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.db.redis import get_redis
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UpdateUserRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.cache import (
    MAX_LOGIN_ATTEMPTS,
    blacklist_token,
    delete_cached_user_profile,
    delete_email_verification_token,
    delete_password_reset_token,
    get_cached_user_profile,
    get_email_verification_token,
    get_login_attempts,
    get_password_reset_token,
    increment_login_attempts,
    is_token_blacklisted,
    reset_login_attempts,
    set_cached_user_profile,
    set_email_verification_token,
    set_password_reset_token,
)
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    mark_user_verified,
    update_user,
    update_user_password,
)
from app.services.event_publisher import publish_user_event
from app.tasks.email import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")
logger = structlog.get_logger(__name__)


def _decode_and_validate_token(token: str, expected_type: str) -> dict:
    """Shared JWT decoding logic. Raises credentials_exception on any failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        token_type = payload.get("type")

        if user_id is None or token_type != expected_type:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return payload


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = _decode_and_validate_token(token, "access")
    user_id = payload["sub"]

    # Check if this specific token has been revoked (e.g. via logout)
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(redis, jti):
        raise credentials_exception

    # Try cache first
    cached_profile = await get_cached_user_profile(redis, int(user_id))
    if cached_profile is not None:
        return cached_profile

    # Cache miss -> DB Query
    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise credentials_exception

    # Cache the profile
    response_data = UserResponse.model_validate(user).model_dump(mode="json")
    await set_cached_user_profile(redis, user.id, response_data)

    return response_data


async def get_current_user_db(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = _decode_and_validate_token(token, "access")
    user_id = payload["sub"]

    # Check if this specific token has been revoked
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(redis, jti):
        raise credentials_exception

    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise credentials_exception
    return user


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_signup)
async def signup(
    request: Request, payload: SignupRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)
):
    existing_email = await get_user_by_email(db, str(payload.email))
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    existing_username = await get_user_by_username(db, payload.username)
    if existing_username is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken",
        )

    password_hash = await hash_password(payload.password)
    try:
        user = await create_user(db, payload, password_hash)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already exists",
        )

    verification_otp = generate_otp()
    await set_email_verification_token(redis, str(user.email), verification_otp)
    logger.info("verification_otp_generated", email=str(user.email))
    send_verification_email.delay(str(user.email), verification_otp)

    await publish_user_event(
        redis,
        "user.created",
        {
            "id": user.id,
            "email": str(user.email),
            "username": user.username,
            "full_name": user.full_name,
            "is_verified": user.is_verified,
        },
    )

    if settings.debug:
        return {"message": f"User registered successfully. Verification OTP: {verification_otp}"}

    return {"message": "User registered successfully. Please verify your email using the OTP."}


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_login)
async def login(
    request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)
):
    attempts = await get_login_attempts(redis, str(payload.email))
    if attempts >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = await get_user_by_email(db, str(payload.email))

    # Timing side-channel fix: always run bcrypt verification even if user doesn't exist.
    # This normalizes response time so attackers can't distinguish "user exists" from "user doesn't".
    if user is None:
        await db.close()
        await verify_password("dummy", DUMMY_HASH)
        await increment_login_attempts(redis, str(payload.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_hash = user.password_hash
    user_id = user.id
    user_is_verified = user.is_verified

    # Release connection back to pool BEFORE doing the slow bcrypt verification!
    await db.close()

    if not await verify_password(payload.password, password_hash):
        await increment_login_attempts(redis, str(payload.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user_is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    await reset_login_attempts(redis, str(payload.email))

    # Open a new short-lived session using the same engine as the request session
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(db.bind, expire_on_commit=False) as new_db:
        await new_db.execute(update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC)))
        await new_db.commit()

    access_token = create_access_token(str(user_id))
    refresh_token = create_refresh_token(str(user_id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_refresh)
async def refresh_token(
    request: Request,
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )

    try:
        decode_payload = jwt.decode(
            payload.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = decode_payload.get("sub")
        token_type = decode_payload.get("type")
        jti = decode_payload.get("jti")

        if user_id is None or token_type != "refresh" or jti is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    if await is_token_blacklisted(redis, jti):
        raise credentials_exception

    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise credentials_exception

    exp = decode_payload.get("exp", 0)
    remaining_ttl = max(int(exp - datetime.now(UTC).timestamp()), 0)
    await blacklist_token(redis, jti, remaining_ttl)

    new_access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    token: str = Depends(oauth2_scheme),
    redis: Redis = Depends(get_redis),
):
    # Blacklist the access token (from Authorization header)
    try:
        access_payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        access_jti = access_payload.get("jti")
        if access_jti:
            exp = access_payload.get("exp", 0)
            remaining_ttl = max(int(exp - datetime.now(UTC).timestamp()), 0)
            await blacklist_token(redis, access_jti, remaining_ttl)
    except JWTError:
        pass

    # Blacklist the refresh token (from request body)
    try:
        refresh_payload = jwt.decode(
            payload.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        refresh_jti = refresh_payload.get("jti")
        if refresh_jti:
            exp = refresh_payload.get("exp", 0)
            remaining_ttl = max(int(exp - datetime.now(UTC).timestamp()), 0)
            await blacklist_token(redis, refresh_jti, remaining_ttl)
    except JWTError:
        pass

    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_forgot_password)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await get_user_by_email(db, str(payload.email))

    if user is not None:
        reset_otp = generate_otp()
        await set_password_reset_token(redis, str(payload.email), reset_otp)
        logger.info("password_reset_otp_generated", email=str(payload.email))
        send_password_reset_email.delay(str(payload.email), reset_otp)

        if settings.debug:
            return {"message": f"Password reset OTP generated: {reset_otp}"}

    return {"message": "If the email exists, password reset instructions are ready."}


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_reset_password)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await get_user_by_email(db, str(payload.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset request",
        )

    stored_token = await get_password_reset_token(redis, str(payload.email))
    if stored_token is None or not hmac.compare_digest(stored_token, payload.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    password_hash = await hash_password(payload.new_password)
    await update_user_password(db, user, password_hash)
    await delete_password_reset_token(redis, str(payload.email))
    await delete_cached_user_profile(redis, user.id)

    return {"message": "Password reset successful"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateUserRequest,
    current_user: User = Depends(get_current_user_db),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        updated_user = await update_user(db, current_user, payload)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    await delete_cached_user_profile(redis, updated_user.id)

    response_data = UserResponse.model_validate(updated_user).model_dump(mode="json")
    await set_cached_user_profile(redis, updated_user.id, response_data)

    await publish_user_event(
        redis,
        "user.updated",
        {
            "id": updated_user.id,
            "email": str(updated_user.email),
            "username": updated_user.username,
            "full_name": updated_user.full_name,
        },
    )

    return response_data


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_verify_email)
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await get_user_by_email(db, str(payload.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification request",
        )

    stored_token = await get_email_verification_token(redis, str(payload.email))
    if stored_token is None or not hmac.compare_digest(stored_token, payload.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    await mark_user_verified(db, user)
    await delete_email_verification_token(redis, str(payload.email))
    await delete_cached_user_profile(redis, user.id)
    send_welcome_email.delay(str(user.email), user.full_name)

    await publish_user_event(
        redis,
        "user.verified",
        {
            "id": user.id,
            "email": str(user.email),
            "is_verified": True,
        },
    )

    return {"message": "Email verified successfully"}


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_resend_verification)
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await get_user_by_email(db, str(payload.email))

    if user is None:
        return {"message": "If the email exists, verification instructions are ready."}

    if user.is_verified:
        return {"message": "Email is already verified"}

    verification_otp = generate_otp()
    await set_email_verification_token(redis, str(payload.email), verification_otp)
    logger.info("verification_otp_regenerated", email=str(payload.email))
    send_verification_email.delay(str(payload.email), verification_otp)

    if settings.debug:
        return {"message": f"Verification OTP generated: {verification_otp}"}

    return {"message": "If the email exists, verification instructions are ready."}
