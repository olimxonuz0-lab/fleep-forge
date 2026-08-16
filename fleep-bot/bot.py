"""
FLEEP FORGE Bot — aiogram 3 entrypoint.

Wires config, the fleep-api client, Redis-backed FSM storage, throttling,
and the transaction-flow router. Run with:

    python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from api_client import FleepApiClient
from config import get_bot_settings
from handlers.transaction_handlers import router as transaction_router
from middlewares.api_client_middleware import ApiClientMiddleware
from middlewares.throttling_middleware import ThrottlingMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fleep.bot")


async def main() -> None:
    settings = get_bot_settings()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    api_client = FleepApiClient(settings)

    dp.update.middleware(ThrottlingMiddleware(redis=redis))
    dp.update.middleware(ApiClientMiddleware(api_client=api_client))
    dp.include_router(transaction_router)

    logger.info("Starting FLEEP FORGE Bot (aiogram 3), webhook mode: %s", settings.use_webhook)

    try:
        if settings.use_webhook:
            # Webhook-mode bootstrapping (aiohttp app + set_webhook) is
            # intentionally left to infra/deploy scripts, which own the
            # public URL and TLS termination — this entrypoint always
            # supports polling for local development regardless of mode.
            await bot.set_webhook(f"{settings.webhook_base_url}{settings.webhook_path}")
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
    finally:
        await api_client.close()
        await bot.session.close()
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
