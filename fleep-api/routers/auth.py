import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.deps import verify_bot_secret
from core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from models.user import User
from schemas.user import TelegramLinkRequest, TokenPair, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenPair:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)) -> TokenPair:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(payload.sub)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer valid")

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post(
    "/telegram-link",
    response_model=UserRead,
    dependencies=[Depends(verify_bot_secret)],
)
async def telegram_link(payload: TelegramLinkRequest, db: AsyncSession = Depends(get_db)) -> User:
    """Called by fleep-bot (server-to-server) to find-or-create a User for
    a Telegram chat. Never exposed to end users directly."""
    result = await db.execute(select(User).where(User.telegram_id == payload.telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
            display_name=payload.display_name,
        )
        db.add(user)
    else:
        user.telegram_username = payload.telegram_username
        user.display_name = payload.display_name

    await db.commit()
    await db.refresh(user)
    return user
