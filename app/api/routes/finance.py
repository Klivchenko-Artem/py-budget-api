"""Категории, операции, бюджеты и отчёт."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import InvalidInputError
from app.db.models import OperationKind
from app.schemas.common import to_first_day
from app.schemas.finance import (
    BudgetCreate,
    BudgetRead,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    MonthlyReport,
    OperationCreate,
    OperationPage,
    OperationRead,
    OperationUpdate,
)
from app.services import budgets, categories, operations, reports

router = APIRouter(prefix="/api", tags=["Финансы"])


def _month_param(month: str | None) -> dt.date:
    """Месяц в запросе в виде «2026-09». Без него берём текущий.

    Кривое значение это ошибка клиента, а не сервиса: голый ValueError отсюда
    никто не ловил, и `?month=2026-9` отдавал пятисотку с трейсбеком.
    """
    if month is None:
        return dt.date.today().replace(day=1)

    parsed = to_first_day(month)

    if not isinstance(parsed, dt.date):
        raise InvalidInputError("месяц указывается как 2026-09")

    return parsed


# --- категории ---


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Завести категорию",
)
async def create_category(
    payload: CategoryCreate, session: SessionDep, user_id: CurrentUser
) -> CategoryRead:
    category = await categories.create(session, user_id, payload.name, payload.kind)

    return CategoryRead.model_validate(category)


@router.get("/categories", response_model=list[CategoryRead], summary="Свои категории")
async def list_categories(
    session: SessionDep,
    user_id: CurrentUser,
    kind: Annotated[OperationKind | None, Query(description="income или expense")] = None,
) -> list[CategoryRead]:
    found = await categories.list_all(session, user_id, kind)

    return [CategoryRead.model_validate(item) for item in found]


@router.patch("/categories/{category_id}", response_model=CategoryRead, summary="Переименовать")
async def rename_category(
    category_id: int, payload: CategoryUpdate, session: SessionDep, user_id: CurrentUser
) -> CategoryRead:
    category = await categories.rename(session, user_id, category_id, payload.name)

    return CategoryRead.model_validate(category)


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить категорию вместе с её операциями",
)
async def delete_category(category_id: int, session: SessionDep, user_id: CurrentUser) -> Response:
    await categories.delete(session, user_id, category_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- операции ---


@router.post(
    "/operations",
    response_model=OperationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Записать трату или поступление",
)
async def create_operation(
    payload: OperationCreate, session: SessionDep, user_id: CurrentUser
) -> OperationRead:
    operation = await operations.create(
        session,
        user_id,
        payload.category_id,
        payload.amount,
        payload.occurred_on,
        payload.note,
    )

    return OperationRead.model_validate(operation)


@router.get("/operations", response_model=OperationPage, summary="Список операций")
async def list_operations(
    session: SessionDep,
    user_id: CurrentUser,
    kind: OperationKind | None = None,
    category_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: Annotated[int, Query(ge=1, le=operations.MAX_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OperationPage:
    items, total = await operations.list_page(
        session,
        user_id,
        kind=kind,
        category_id=category_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return OperationPage(
        items=[OperationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/operations/{operation_id}", response_model=OperationRead, summary="Поправить операцию"
)
async def update_operation(
    operation_id: int,
    payload: OperationUpdate,
    session: SessionDep,
    user_id: CurrentUser,
) -> OperationRead:
    operation = await operations.update(
        session,
        user_id,
        operation_id,
        category_id=payload.category_id,
        amount=payload.amount,
        occurred_on=payload.occurred_on,
        note=payload.note,
        # Пустое примечание и «не трогай примечание» это разные намерения,
        # различаем их по тому, пришло ли поле вообще
        note_given="note" in payload.model_fields_set,
    )

    return OperationRead.model_validate(operation)


@router.delete(
    "/operations/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить операцию",
)
async def delete_operation(
    operation_id: int, session: SessionDep, user_id: CurrentUser
) -> Response:
    await operations.delete(session, user_id, operation_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- бюджеты ---


@router.put("/budgets", response_model=BudgetRead, summary="Поставить лимит на месяц")
async def set_budget(
    payload: BudgetCreate, session: SessionDep, user_id: CurrentUser
) -> BudgetRead:
    budget = await budgets.set_limit(
        session, user_id, payload.category_id, payload.month, payload.limit_amount
    )

    return BudgetRead.model_validate(budget)


@router.get("/budgets", response_model=list[BudgetRead], summary="Лимиты за месяц")
async def list_budgets(
    session: SessionDep,
    user_id: CurrentUser,
    month: Annotated[str | None, Query(description="Месяц вида 2026-09")] = None,
) -> list[BudgetRead]:
    found = await budgets.list_for_month(session, user_id, _month_param(month))

    return [BudgetRead.model_validate(item) for item in found]


@router.delete(
    "/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Снять лимит"
)
async def delete_budget(budget_id: int, session: SessionDep, user_id: CurrentUser) -> Response:
    await budgets.delete(session, user_id, budget_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- отчёт ---


@router.get("/reports/monthly", response_model=MonthlyReport, summary="Отчёт за месяц")
async def monthly_report(
    session: SessionDep,
    user_id: CurrentUser,
    month: Annotated[str | None, Query(description="Месяц вида 2026-09")] = None,
) -> MonthlyReport:
    return await reports.monthly(session, user_id, _month_param(month))
