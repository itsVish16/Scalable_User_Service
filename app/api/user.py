from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from redis.asyncio import Redis

from app.core.rate_limit import limiter

from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer


from app.config import settings
from app.db.database import get_db
from app.db.redis import get_redis
from app.services.cache import get_cached_user_profile, set_cached_user_profile
from app.models.user import User
from app.core.security import create_access_token, create_refresh_token
from app.services.user_service import (
    check_user_password,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
)
from app.schemas.user import (
    LoginRequest,
    MessageResponse,
    SignupRequest,
    TokenResponse,
    UserResponse,
    RefreshTokenRequest,
)

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl= "/users/login")

async def get_current_user(
    token:str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail = "Could not validate credentials",
        headers = {"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token,settings.secret_key, algorithms = [settings.algorithm])
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
async def signup(request: Request,payload: SignupRequest, db: AsyncSession = Depends(get_db)):
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
        await create_user(db, payload)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already exists"
        )

    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request,payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, str(payload.email))

    if user is None or not check_user_password(user, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))



    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_token(request: Request, payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    credentials_exception= HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail = "Invalid refresh token",
    )

    try:
        decode_payload = jwt.decode(
            payload.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = decode_payload.get("sub")
        token_type = decode_payload.get("type")

        if user_id is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise credentials_exception
    
    new_access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type":"bearer"
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user), redis: Redis = Depends(get_redis)):
    cached_profile = await get_cached_user_profile(redis, current_user.id)
    if cached_profile is not None:
        return cached_profile
    
    response_data = UserResponse.model_validate(current_user).model_dump(mode = "json")
    await set_cached_user_profile(redis, current_user.id, response_data)

    return response_data


    
    

