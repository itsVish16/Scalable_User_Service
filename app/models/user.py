from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, autoincrement = True)
    username: Mapped[str] = mapped_column(String(50), unique = True, index = True, nullable = False)
    email: Mapped[str] = mapped_column(String(255), unique = True, index = True, nullable = False)
    full_name: Mapped[str] = mapped_column(String(100),nullable = False)
    password_hash: Mapped[str] = mapped_column(String(255) , nullable = False)

    is_verified: Mapped[bool] = mapped_column(Boolean, nullable = False, default = False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        default = lambda: datetime.now(timezone.utc),
        nullable = False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
        nullable = False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
