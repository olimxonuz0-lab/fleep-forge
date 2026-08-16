import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_db

router = APIRouter(tags=["health"])
settings = get_settings()

_start_time = time.monotonic()


@router.get("/")
async def root() -> dict:
    return {"status": "active", "service": "fleep-api", "version": settings.app_version}


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    checks = {"database": "unknown", "redis": "unknown"}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"

    try:
        client = aioredis.from_url(str(settings.redis_url))
        await client.ping()
        await client.close()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {
        "healthy": healthy,
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "checks": checks,
    }
