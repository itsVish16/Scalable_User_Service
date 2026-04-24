from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
)
from app.db.database import get_db
from app.db.redis import get_redis
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
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
    check_user_password,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    mark_user_verified,
    update_last_login,
    update_user,
    update_user_password,
)
from app.tasks.email import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        token_type = payload.get("type")

        if user_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise credentials_exception
    return user


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
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

    try:
        user = await create_user(db, payload)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already exists",
        )

    verification_otp = generate_otp()
    await set_email_verification_token(redis, str(user.email), verification_otp)
    send_welcome_email.delay(str(user.email), user.full_name)
    send_verification_email.delay(str(user.email), verification_otp)

    if settings.debug:
        return {"message": f"User registered successfully. Verification OTP: {verification_otp}"}

    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
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

    if user is None or not await check_user_password(user, payload.password):
        await increment_login_attempts(redis, str(payload.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    await reset_login_attempts(redis, str(payload.email))
    await update_last_login(db, user)

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
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
    from datetime import datetime

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
async def logout(payload: RefreshTokenRequest, redis: Redis = Depends(get_redis)):
    try:
        decode_payload = jwt.decode(
            payload.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        jti = decode_payload.get("jti")
        if jti:
            exp = decode_payload.get("exp", 0)
            from datetime import datetime

            remaining_ttl = max(int(exp - datetime.now(UTC).timestamp()), 0)
            await blacklist_token(redis, jti, remaining_ttl)
    except JWTError:
        pass

    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
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
        send_password_reset_email.delay(str(payload.email), reset_otp)

        if settings.debug:
            return {"message": f"Password reset OTP generated: {reset_otp}"}

    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
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
    if stored_token is None or stored_token != payload.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    await update_user_password(db, user, payload.new_password)
    await delete_password_reset_token(redis, str(payload.email))
    await delete_cached_user_profile(redis, user.id)

    return {"message": "Password reset successful"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user), redis: Redis = Depends(get_redis)):
    cached_profile = await get_cached_user_profile(redis, current_user.id)
    if cached_profile is not None:
        return cached_profile

    response_data = UserResponse.model_validate(current_user).model_dump(mode="json")
    await set_cached_user_profile(redis, current_user.id, response_data)

    return response_data


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
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

    return response_data


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit("5/minute")
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
    if stored_token is None or stored_token != payload.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    await mark_user_verified(db, user)
    await delete_email_verification_token(redis, str(payload.email))
    await delete_cached_user_profile(redis, user.id)

    return {"message": "Email verified successfully"}


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("5/minute")
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    user = await get_user_by_email(db, str(payload.email))

    if user is None:
        return {"message": "If the email exists, a verification email has been sent"}

    if user.is_verified:
        return {"message": "Email is already verified"}

    verification_otp = generate_otp()
    await set_email_verification_token(redis, str(payload.email), verification_otp)
    send_verification_email.delay(str(payload.email), verification_otp)

    if settings.debug:
        return {"message": f"Verification OTP generated: {verification_otp}"}

    return {"message": "If the email exists, a verification email has been sent"}
