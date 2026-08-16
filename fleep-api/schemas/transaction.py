import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.transaction import TransactionStatus


class TransactionCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    amount: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    payload: dict[str, Any] = Field(default_factory=dict)


class TransactionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: Optional[str]
    to_status: str
    reason: Optional[str]
    actor: str
    created_at: datetime


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    status: TransactionStatus
    amount: Optional[float]
    currency: Optional[str]
    payload: dict[str, Any]
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class TransactionDetail(TransactionRead):
    events: list[TransactionEventRead] = Field(default_factory=list)


class TransactionTransitionRequest(BaseModel):
    to_status: TransactionStatus
    reason: Optional[str] = None
