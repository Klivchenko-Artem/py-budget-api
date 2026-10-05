"""Общая подготовка тестов: своя база, чистый Redis, готовый клиент."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Окружение подменяется до импорта приложения: настройки читаются один раз
# и кешируются, потом их уже не переспросить.
#
# База и номер базы Redis выбираются принудительно, а не через setdefault:
# в контейнере DATABASE_URL уже указывает на рабочую базу, и мягкая подстановка
# оставила бы её, а тесты в конце сносят всю схему. Один раз так и вышло.
_database_url = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://budget:budget@postgres:5432/budget"
)

if not _database_url.endswith("_test"):
    _database_url += "_test"

_redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

os.environ["DATABASE_URL"] = _database_url
# Своя база Redis: тесты чистят её целиком, и рабочий кеш под руку попадать не должен
os.environ["REDIS_URL"] = _redis_url.rsplit("/", 1)[0] + "/1"
os.environ.setdefault("JWT_SECRET", "тестовый-секрет-подлиннее-16")
os.environ.setdefault("REPORT_CACHE_TTL_SECONDS", "60")

from app.core import cache
from app.core.config import get_settings
from app.db.models import Base
from app.db.session import get_engine
from app.main import app

TABLES = ("operations", "budgets", "categories", "users")


@pytest.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    """Заводит тестовую базу и схему в ней."""
    settings = get_settings()
    admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    db_name = settings.database_url.rsplit("/", 1)[1]

    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    async with admin.connect() as connection:
        exists = await connection.scalar(
            text("select 1 from pg_database where datname = :name"), {"name": db_name}
        )

        if not exists:
            await connection.execute(text(f'create database "{db_name}"'))

    await admin.dispose()

    engine = get_engine()

    # Схему поднимаем метаданными, а не миграциями: тесты про поведение API,
    # а сами миграции проверяются отдельным шагом в CI на чистой базе
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    """Каждый тест начинает с пустой базы и пустого кеша."""
    engine = get_engine()

    async with engine.begin() as connection:
        await connection.execute(text(f"truncate {', '.join(TABLES)} restart identity cascade"))

    await cache.get_client().flushdb()

    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def token(client: AsyncClient) -> str:
    """Зарегистрированный пользователь и его токен."""
    response = await client.post(
        "/api/auth/register",
        json={"email": "artem@example.com", "password": "паролькудлиннее"},
    )
    response.raise_for_status()

    return response.json()["token"]["access_token"]


@pytest.fixture
def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def categories(client: AsyncClient, auth: dict[str, str]) -> dict[str, int]:
    """Три категории на все случаи: зарплата, еда, такси."""
    created = {}

    for name, kind in (("Зарплата", "income"), ("Еда", "expense"), ("Такси", "expense")):
        response = await client.post(
            "/api/categories", json={"name": name, "kind": kind}, headers=auth
        )
        created[name] = response.json()["id"]

    return created
