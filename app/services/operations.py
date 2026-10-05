"""Операции: траты и поступления."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.errors import NotFoundError
from app.db.models import Operation, OperationKind
from app.services import categories

MAX_LIMIT = 100


async def create(
    session: AsyncSession,
    user_id: int,
    category_id: int,
    amount: Decimal,
    occurred_on: dt.date,
    note: str | None,
) -> Operation:
    # Вид операции не спрашиваем у клиента: он однозначно берётся из категории,
    # иначе завелась бы трата в категории доходов
    category = await categories.get_owned(session, user_id, category_id)

    operation = Operation(
        user_id=user_id,
        category_id=category.id,
        amount=amount,
        kind=category.kind,
        occurred_on=occurred_on,
        note=note,
    )
    session.add(operation)
    await session.flush()

    cache.drop_later(session, cache.report_key(user_id, occurred_on))

    return operation


async def get_owned(session: AsyncSession, user_id: int, operation_id: int) -> Operation:
    operation = await session.scalar(
        select(Operation).where(Operation.id == operation_id, Operation.user_id == user_id)
    )

    if operation is None:
        raise NotFoundError("операция не найдена")

    return operation


def _filtered(
    user_id: int,
    kind: OperationKind | None,
    category_id: int | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
) -> Select:
    query = select(Operation).where(Operation.user_id == user_id)

    if kind is not None:
        query = query.where(Operation.kind == kind)

    if category_id is not None:
        query = query.where(Operation.category_id == category_id)

    if date_from is not None:
        query = query.where(Operation.occurred_on >= date_from)

    if date_to is not None:
        query = query.where(Operation.occurred_on <= date_to)

    return query


async def list_page(
    session: AsyncSession,
    user_id: int,
    *,
    kind: OperationKind | None = None,
    category_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Operation], int]:
    """Страница операций и общее количество под теми же фильтрами."""
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    query = _filtered(user_id, kind, category_id, date_from, date_to)

    # Считаем в базе, а не длиной выборки: иначе пришлось бы тянуть все строки
    # ради одного числа
    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    result = await session.scalars(
        query.order_by(Operation.occurred_on.desc(), Operation.id.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(result), int(total or 0)


async def update(
    session: AsyncSession,
    user_id: int,
    operation_id: int,
    *,
    category_id: int | None = None,
    amount: Decimal | None = None,
    occurred_on: dt.date | None = None,
    note: str | None = None,
    note_given: bool = False,
) -> Operation:
    operation = await get_owned(session, user_id, operation_id)
    old_date = operation.occurred_on

    if category_id is not None:
        category = await categories.get_owned(session, user_id, category_id)
        operation.category_id = category.id
        # Перенос в категорию другого вида меняет и вид самой операции
        operation.kind = category.kind

    if amount is not None:
        operation.amount = amount

    if occurred_on is not None:
        operation.occurred_on = occurred_on

    if note_given:
        operation.note = note

    await session.flush()

    # Операция могла переехать в другой месяц, сбрасываем оба отчёта
    cache.drop_later(
        session,
        cache.report_key(user_id, old_date),
        cache.report_key(user_id, operation.occurred_on),
    )

    return operation


async def delete(session: AsyncSession, user_id: int, operation_id: int) -> None:
    operation = await get_owned(session, user_id, operation_id)
    month = operation.occurred_on

    await session.delete(operation)
    await session.flush()
    cache.drop_later(session, cache.report_key(user_id, month))
