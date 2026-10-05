"""Подключение к базе: движок и сессии."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import cache
from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Движок один на процесс: внутри него живёт пул соединений."""
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=5,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )

    return _session_factory


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Сессия на запрос: коммит по успеху, откат по исключению."""
    factory = get_session_factory()

    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        # Кеш чистим только после успешного коммита: до него изменения ещё
        # не видны другим запросам, и сброшенный ключ тут же заполнился бы
        # прежним значением
        await cache.flush_pending(session)


async def dispose_engine() -> None:
    """Закрывает пул при остановке приложения."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None
