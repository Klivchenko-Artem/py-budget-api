"""Точка входа: приложение, обработчики ошибок, служебные ручки."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from redis import RedisError
from sqlalchemy import text

from app.api.routes import auth, finance
from app.core import cache
from app.core.config import get_settings
from app.core.errors import (
    AlreadyExistsError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    UnauthorizedError,
)
from app.db.session import dispose_engine, get_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Перевод ошибок предметной области в коды ответа собран в одном месте:
# сервисы про HTTP ничего не знают
STATUS_BY_ERROR = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    AlreadyExistsError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield

    # Пул соединений и клиент Redis закрываются явно: иначе на остановке
    # в логах остаются жалобы на брошенные соединения
    await dispose_engine()
    await cache.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        summary="Учёт доходов, расходов и бюджетов с отчётом за месяц",
        lifespan=lifespan,
    )

    app.include_router(auth.router)
    app.include_router(finance.router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        code = STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)

        return JSONResponse(status_code=code, content={"detail": exc.message})

    @app.get("/healthz", tags=["Служебное"], summary="Жив ли процесс")
    async def healthz() -> dict[str, str]:
        # Про сам процесс и ничего больше: если проверять здесь базу, моргнувший
        # Postgres перезапустит все поды разом
        return {"status": "ok"}

    @app.get("/readyz", tags=["Служебное"], summary="Готов ли обслуживать")
    async def readyz() -> JSONResponse:
        checks = {"postgres": "ok", "redis": "ok"}

        try:
            async with get_session_factory()() as session:
                await session.execute(text("select 1"))
        except Exception:
            checks["postgres"] = "down"

        try:
            await cache.get_client().ping()
        except (RedisError, OSError):
            checks["redis"] = "down"

        ready = all(value == "ok" for value in checks.values())

        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={**checks, "status": "ready" if ready else "not ready"},
        )

    return app


app = create_app()
