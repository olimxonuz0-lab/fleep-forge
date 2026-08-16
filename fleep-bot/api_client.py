"""
Thin async client the bot uses to talk to fleep-api.

Kept deliberately small and dependency-light (httpx only) rather than
pulling in a full generated SDK — the bot only needs a handful of
endpoints, and a hand-written client keeps the failure modes (timeouts,
5xx from the API) explicit at each call site.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from config import BotSettings

logger = logging.getLogger("fleep.bot.api_client")


class FleepApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"fleep-api error {status_code}: {detail}")


class FleepApiClient:
    def __init__(self, settings: BotSettings):
        self._settings = settings
        self._client = httpx.AsyncClient(base_url=settings.api_base_url, timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def link_telegram_user(
        self, telegram_id: int, telegram_username: Optional[str], display_name: str
    ) -> dict[str, Any]:
        resp = await self._client.post(
            "/api/v1/auth/telegram-link",
            json={
                "telegram_id": telegram_id,
                "telegram_username": telegram_username,
                "display_name": display_name,
            },
            headers={"X-Bot-Secret": self._settings.api_bot_secret},
        )
        return self._unwrap(resp)

    async def create_transaction(
        self,
        access_token: str,
        *,
        kind: str,
        idempotency_key: str,
        amount: Optional[float] = None,
        currency: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> dict[str, Any]:
        resp = await self._client.post(
            "/api/v1/transactions",
            json={
                "kind": kind,
                "idempotency_key": idempotency_key,
                "amount": amount,
                "currency": currency,
                "payload": payload or {},
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return self._unwrap(resp)

    async def list_transactions(self, access_token: str, limit: int = 5) -> list[dict[str, Any]]:
        resp = await self._client.get(
            "/api/v1/transactions",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return self._unwrap(resp)

    @staticmethod
    def _unwrap(resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise FleepApiError(resp.status_code, detail)
        return resp.json()
