"""
FLEEP FORGE API — application entrypoint.

Wires together config, database lifecycle, routers, CORS, and structured
exception handling. Run with:

    uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import get_settings
from core.database import engine
from routers import auth, health, realtime, transactions
from transactions.state_machine import InvalidTransitionError, TransactionNotFoundError

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to warm up today beyond the lazily-created engine,
    # but this is where a connection-pool warmup or cache preload would go.
    yield
    # Shutdown: dispose the engine's connection pool cleanly.
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(transactions.router)
    app.include_router(realtime.router)

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition_handler(request: Request, exc: InvalidTransitionError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(TransactionNotFoundError)
    async def transaction_not_found_handler(request: Request, exc: TransactionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    return app


app = create_app()
