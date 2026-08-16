from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from .mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .user import User


class TransactionStatus(str, enum.Enum):
    """States of the transaction state machine.

    Valid transitions are enforced in transactions/state_machine.py, not
    here — this enum only declares the vocabulary.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    CANCELLED = "cancelled"


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user: Mapped["User"] = relationship(back_populates="transactions")

    # Idempotency key supplied by the caller (bot handler or API client) so
    # retried webhook deliveries never double-process the same intent.
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True,
    )

    amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    events: Mapped[List["TransactionEvent"]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionEvent.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transaction id={self.id} kind={self.kind!r} status={self.status.value}>"


class TransactionEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only event log for a transaction (event sourcing).

    Every state transition is recorded here so the current `status` on
    Transaction is always reconstructible / auditable, and so the
    Knowledge Distillation pipeline has a durable source of "what actually
    happened" to summarize into the vault.
    """
    __tablename__ = "transaction_events"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    transaction: Mapped["Transaction"] = relationship(back_populates="events")

    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
