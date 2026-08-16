"""Reusable ORM mixins."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    # sqlalchemy.Uuid (2.0+) renders as native UUID on Postgres and as
    # CHAR(32)/BLOB on backends without a native type (e.g. SQLite in
    # unit tests) — deliberately dialect-agnostic so the same models work
    # against the sqlite+aiosqlite fixture in tests/conftest.py.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
