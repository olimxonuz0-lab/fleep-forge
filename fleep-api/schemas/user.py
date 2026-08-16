import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: Optional[EmailStr]
    telegram_id: Optional[int]
    telegram_username: Optional[str]
    display_name: str
    is_active: bool
    created_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TelegramLinkRequest(BaseModel):
    """Payload the bot sends the API to link/create a user from a Telegram
    chat, verified via telegram_webhook_secret rather than a user JWT."""
    telegram_id: int
    telegram_username: Optional[str] = None
    display_name: str
