from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


def validate_password_strength(v: str) -> str:
    """Shared password validation rules. Used by SignupRequest and ResetPasswordRequest."""
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(v) > 128:
        raise ValueError("Password must be at most 128 characters")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one number")
    return v


def normalize_email(v: str) -> str:
    """Shared email normalization. Used across all request schemas with email fields."""
    return v.strip().lower()


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 30:
            raise ValueError("Username must be 3-30 characters")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Username can only contain letters, numbers, and underscores")
        if v[0].isdigit():
            raise ValueError("Username cannot start with a number")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 100:
            raise ValueError("Full name must be at most 100 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or len(value) != 6:
            raise ValueError("OTP must be exactly 6 digits")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_strength(value)


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)


class UpdateUserRequest(BaseModel):
    username: str | None = None
    full_name: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()

        if len(value) < 3 or len(value) > 30:
            raise ValueError("Username must be 3-30 characters")

        if not all(char.isalnum() or char == "_" for char in value):
            raise ValueError("Username can only contain letters, numbers, and underscores")

        if value[0].isdigit():
            raise ValueError("Username cannot start with a number")

        return value.lower()

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) > 100:
            raise ValueError("Full name must be at most 100 characters")
        return value


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    token: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or len(value) != 6:
            raise ValueError("OTP must be exactly 6 digits")
        return value


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
