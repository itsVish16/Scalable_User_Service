from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer


from app.config import settings
from app.db.database import get_db
from app.core.security import create_access_token, create_refresh_token, 
from app.schemas.user import LoginRequest, MessageResponse, SignupRequest
from app.services.user_service import (
    check_user_password,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
)
from app.sehemas.user import (
    LoginRequest,
    MessageResponse,
    SignupRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl= "/users/login")

async def get_current_user(
    token:Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail = "Could not validate credentials",
        headers = {"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt_decode(toekn,settings.secret_key, algorigthms = [settings.algirithm])
        user_id = payload.get("sub")
        token_type = payload.get("type")

        if user_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_id(db, int(user_id))
    if user in None:
        raise credentials_exception
    return user


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
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
            detail="Email or username already exits"
        )

    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, str(payload.email))

    if user is None or not check_user_password(user, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(str(user.id))
    create_refresh_token = create_refresh_token(str(user.id))



    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


