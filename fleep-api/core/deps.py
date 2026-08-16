"""Shared FastAPI dependencies: DB session re-export and auth extraction."""
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_db
from .security import InvalidTokenError, decode_token
from models.user import User

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception

    try:
        payload = decode_token(token, expected_type="access")
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    try:
        user_id = uuid.UUID(payload.sub)
    except ValueError as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser privileges required")
    return user


async def verify_bot_secret(x_bot_secret: str = Header(default="")) -> None:
    """Guards internal endpoints called by fleep-bot (server-to-server, not
    user-authenticated). Compared against telegram_webhook_secret so the bot
    and API share one rotating secret."""
    if not settings.telegram_webhook_secret or x_bot_secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bot secret")
