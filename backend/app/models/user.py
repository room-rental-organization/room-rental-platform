from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Identity, Integer, String, UniqueConstraint, func, false
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="users_email_key"),
        UniqueConstraint("phone_no", name="users_phone_no_key"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone_no: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    business_name: Mapped[str | None] = mapped_column(String(150))
    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    email_verification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
    )
