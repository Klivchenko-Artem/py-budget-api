"""Категории доходов и расходов."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.errors import AlreadyExistsError, NotFoundError
from app.db.models import Category, OperationKind


async def create(session: AsyncSession, user_id: int, name: str, kind: OperationKind) -> Category:
    category = Category(user_id=user_id, name=name.strip(), kind=kind)
    session.add(category)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AlreadyExistsError("такая категория уже есть") from exc

    return category


async def list_all(
    session: AsyncSession, user_id: int, kind: OperationKind | None = None
) -> list[Category]:
    query = select(Category).where(Category.user_id == user_id)

    if kind is not None:
        query = query.where(Category.kind == kind)

    result = await session.scalars(query.order_by(Category.kind, Category.name))

    return list(result)


async def get_owned(session: AsyncSession, user_id: int, category_id: int) -> Category:
    """Достаёт категорию пользователя.

    Чужая категория отвечает «не найдено», а не «нет доступа»: иначе по коду
    ответа можно проверять, существует ли она у соседа.
    """
    category = await session.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )

    if category is None:
        raise NotFoundError("категория не найдена")

    return category


async def rename(session: AsyncSession, user_id: int, category_id: int, name: str) -> Category:
    category = await get_owned(session, user_id, category_id)
    category.name = name.strip()

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AlreadyExistsError("категория с таким названием уже есть") from exc

    cache.drop_user_later(session, user_id)

    return category


async def delete(session: AsyncSession, user_id: int, category_id: int) -> None:
    """Удаляет категорию вместе с её операциями и бюджетами.

    Сброс кеша здесь общий: операции могли быть в любых месяцах, и вычислять
    затронутые дешевле одним махом.
    """
    category = await get_owned(session, user_id, category_id)

    await session.delete(category)
    await session.flush()
    cache.drop_user_later(session, user_id)
