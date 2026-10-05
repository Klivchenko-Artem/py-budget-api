"""Отчёт за месяц: доходы, расходы, разбивка по категориям, исполнение бюджетов."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import get_settings
from app.db.models import Budget, Category, Operation, OperationKind
from app.schemas.finance import BudgetProgress, CategoryTotal, MonthlyReport

ZERO = Decimal("0.00")


def month_bounds(month: dt.date) -> tuple[dt.date, dt.date]:
    """Первое и последнее число месяца."""
    start = month.replace(day=1)

    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)

    return start, next_month - dt.timedelta(days=1)


async def monthly(session: AsyncSession, user_id: int, month: dt.date) -> MonthlyReport:
    """Отчёт за месяц. Считается в базе, результат кладётся в кеш."""
    start, end = month_bounds(month)

    cached = await cache.get_json(cache.report_key(user_id, start))
    if cached is not None:
        return MonthlyReport.model_validate(cached)

    report = await _build(session, user_id, start, end)

    await cache.set_json(
        cache.report_key(user_id, start),
        report.model_dump(mode="json"),
        get_settings().report_cache_ttl_seconds,
    )

    return report


async def _build(
    session: AsyncSession, user_id: int, start: dt.date, end: dt.date
) -> MonthlyReport:
    # Суммы считает база: тянуть тысячи строк в питон, чтобы сложить их циклом,
    # верный способ получить медленный отчёт на втором году использования
    totals_query = (
        select(
            Category.id,
            Category.name,
            Operation.kind,
            func.sum(Operation.amount).label("total"),
            func.count(Operation.id).label("count"),
        )
        .join(Category, Category.id == Operation.category_id)
        .where(
            Operation.user_id == user_id,
            Operation.occurred_on >= start,
            Operation.occurred_on <= end,
        )
        .group_by(Category.id, Category.name, Operation.kind)
        .order_by(func.sum(Operation.amount).desc())
    )

    by_category: list[CategoryTotal] = []
    income = ZERO
    expense = ZERO
    spent_by_category: dict[int, Decimal] = {}

    for category_id, name, kind, total, count in await session.execute(totals_query):
        total = Decimal(total).quantize(Decimal("0.01"))

        by_category.append(
            CategoryTotal(
                category_id=category_id,
                category_name=name,
                kind=kind,
                total=total,
                operations=count,
            )
        )

        if kind is OperationKind.INCOME:
            income += total
        else:
            expense += total
            spent_by_category[category_id] = total

    budgets_query = (
        select(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.user_id == user_id, Budget.month == start)
        .order_by(Category.name)
    )

    budgets: list[BudgetProgress] = []

    for budget, category_name in await session.execute(budgets_query):
        spent = spent_by_category.get(budget.category_id, ZERO)
        limit_amount = Decimal(budget.limit_amount)

        budgets.append(
            BudgetProgress(
                category_id=budget.category_id,
                category_name=category_name,
                limit_amount=limit_amount,
                spent=spent,
                # Остаток не уводим в минус: перерасход виден по флагу,
                # а «сколько ещё можно» ниже нуля не бывает
                left=max(limit_amount - spent, ZERO),
                used_percent=round(float(spent / limit_amount * 100), 1),
                exceeded=spent > limit_amount,
            )
        )

    return MonthlyReport(
        month=start,
        income=income,
        expense=expense,
        balance=income - expense,
        by_category=by_category,
        budgets=budgets,
    )
