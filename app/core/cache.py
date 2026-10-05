"""Кеш отчётов в Redis.

Отчёт за месяц это несколько агрегатов по всем операциям пользователя.
Считать его на каждый показ незачем: он меняется только когда меняются деньги.

Ошибки Redis наружу не всплывают: кеш ускоряет, но не является источником
правды, и его недоступность не должна ронять API.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from redis import RedisError
from redis.asyncio import Redis, from_url

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_client() -> Redis:
    global _client

    if _client is None:
        _client = from_url(get_settings().redis_url, decode_responses=True)

    return _client


def report_key(user_id: int, month: dt.date) -> str:
    return f"report:{user_id}:{month:%Y-%m}"


async def get_json(key: str) -> Any | None:
    try:
        raw = await get_client().get(key)
    except RedisError as exc:
        logger.warning("кеш не ответил на чтение: %s", exc)
        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # В кеше мусор, ведём себя так, будто его там и не было
        return None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await get_client().set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
    except RedisError as exc:
        logger.warning("кеш не ответил на запись: %s", exc)


async def drop(*keys: str) -> None:
    """Точечный сброс: знаем, какой месяц поехал, его и выбрасываем."""
    if not keys:
        return

    try:
        await get_client().delete(*keys)
    except RedisError as exc:
        logger.warning("кеш не ответил на удаление: %s", exc)


def drop_later(session: Any, *keys: str) -> None:
    """Откладывает сброс ключей до коммита.

    Сбрасывать кеш сразу нельзя: изменение ещё не закоммичено, и параллельный
    запрос успевает положить в кеш прежнюю сумму, на весь срок жизни записи.
    Человек добавил трату и пять минут не видит её в отчёте.
    """
    pending: set[str] = session.info.setdefault("cache_drops", set())
    pending.update(keys)


def drop_user_later(session: Any, user_id: int) -> None:
    """То же для «сбросить всё, что есть у пользователя»."""
    users: set[int] = session.info.setdefault("cache_drop_users", set())
    users.add(user_id)


async def flush_pending(session: Any) -> None:
    """Сбрасывает то, что накопилось за транзакцию. Зовётся после коммита."""
    keys: set[str] = session.info.pop("cache_drops", set())
    users: set[int] = session.info.pop("cache_drop_users", set())

    if keys:
        await drop(*keys)

    for user_id in users:
        await drop_user(user_id)


async def drop_user(user_id: int) -> None:
    """Сброс всех отчётов пользователя, когда поехать могло что угодно."""
    try:
        client = get_client()
        async for key in client.scan_iter(match=f"report:{user_id}:*", count=100):
            await client.delete(key)
    except RedisError as exc:
        logger.warning("кеш не ответил на очистку: %s", exc)


async def close() -> None:
    global _client

    if _client is not None:
        await _client.aclose()

    _client = None
