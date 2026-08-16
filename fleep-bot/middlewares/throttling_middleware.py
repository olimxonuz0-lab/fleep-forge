"""Per-user rate limiting middleware backed by Redis, so a burst of button
taps or repeated /commands can't hammer fleep-api."""
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from redis.asyncio import Redis


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, rate_limit_seconds: float = 0.7):
        self._redis = redis
        self._rate_limit_seconds = rate_limit_seconds
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None and isinstance(event, Update):
            user = getattr(getattr(event, event.event_type, None), "from_user", None)

        if user is not None:
            key = f"throttle:{user.id}"
            # SET ... NX with an expiry acts as a cheap distributed lock:
            # if the key already exists, this user is within the cooldown
            # window and the update is dropped rather than queued, so
            # handlers never pile up behind a slow upstream call.
            allowed = await self._redis.set(key, "1", nx=True, px=int(self._rate_limit_seconds * 1000))
            if not allowed:
                return None

        return await handler(event, data)
