"""Бюджеты: потолок трат по категории на месяц."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.errors import InvalidInputError, NotFoundError
from app.db.models import Budget, OperationKind
from app.services import categories


async def set_limit(
    session: AsyncSession,
    user_id: int,
    category_id: int,
    month: dt.date,
    limit_amount: Decimal,
) -> Budget:
    """Заводит или переписывает лимит.

    Повторная установка лимита это обычное дело («в этом месяце можно больше»),
    поэтому это одна операция, а не «создать» и «изменить» по отдельности.
    """
    category = await categories.get_owned(session, user_id, category_id)

    if category.kind is not OperationKind.EXPENSE:
        raise InvalidInputError("бюджет ставится только на категорию расходов")

    month = month.replace(day=1)

    budget = await session.scalar(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.category_id == category_id,
            Budget.month == month,
        )
    )

    if budget is None:
        budget = Budget(
            user_id=user_id,
            category_id=category_id,
            month=month,
            limit_amount=limit_amount,
        )
        session.add(budget)
    else:
        budget.limit_amount = limit_amount

    await session.flush()
    cache.drop_later(session, cache.report_key(user_id, month))

    return budget


async def list_for_month(session: AsyncSession, user_id: int, month: dt.date) -> list[Budget]:
    month = month.replace(day=1)

    result = await session.scalars(
        select(Budget)
        .where(Budget.user_id == user_id, Budget.month == month)
        .order_by(Budget.category_id)
    )

    return list(result)


async def delete(session: AsyncSession, user_id: int, budget_id: int) -> None:
    budget = await session.scalar(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
    )

    if budget is None:
        raise NotFoundError("бюджет не найден")

    month = budget.month

    await session.delete(budget)
    await session.flush()
    cache.drop_later(session, cache.report_key(user_id, month))
