from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if(len(v) < 3 or len(v) > 30):
            raise ValueError("Username must be 3-30 character")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Username can only contain letters, number, and underscores")
        if v[0].isdigit():
            raise ValueError("Username cannot start with a number")
        return v.lower()
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppeercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v
    
class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v, str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Otp must be exactly 6 digits")
        return v

class ResendOtpRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    @field_validator("otp")
    @classmethod
    def validateOtp(cls, v, str) -> str:
        v = v.strip()
        if not v.digit() or len(v) != 6:
            raise ValueError("Otp must be exactly 6 digits")
        return v
    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppeercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v

class MessageResponse(BaseModel):
    message: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    
    
