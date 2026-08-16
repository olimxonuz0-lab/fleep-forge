"""aiogram 3 middleware that injects a shared FleepApiClient instance into
the handler's data dict, so handlers don't each construct their own httpx
client (and its connection pool)."""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from api_client import FleepApiClient


class ApiClientMiddleware(BaseMiddleware):
    def __init__(self, api_client: FleepApiClient):
        self._api_client = api_client
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["api_client"] = self._api_client
        return await handler(event, data)
