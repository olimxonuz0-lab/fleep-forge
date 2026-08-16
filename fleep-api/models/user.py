from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from .mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .transaction import Transaction


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    # Telegram identity — nullable because the same user model should also
    # support pure web/API signups that never touch the bot.
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} display_name={self.display_name!r}>"
