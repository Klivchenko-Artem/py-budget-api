"""Схемы категорий, операций, бюджетов и отчёта."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import OperationKind
from app.schemas.common import Money, Month, PositiveMoney

# --- категории ---


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: OperationKind


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: OperationKind


# --- операции ---


class OperationCreate(BaseModel):
    category_id: int
    amount: PositiveMoney
    occurred_on: dt.date
    note: str | None = Field(default=None, max_length=255)


class OperationUpdate(BaseModel):
    """Правка операции: приходит только то, что меняют."""

    category_id: int | None = None
    amount: PositiveMoney | None = None
    occurred_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=255)


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    amount: Money
    kind: OperationKind
    occurred_on: dt.date
    note: str | None


class OperationPage(BaseModel):
    """Страница списка. Общее число отдаём отдельно, по нему рисуют пагинацию."""

    items: list[OperationRead]
    total: int
    limit: int
    offset: int


# --- бюджеты ---


class BudgetCreate(BaseModel):
    category_id: int
    month: Month
    limit_amount: PositiveMoney


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    month: Month
    limit_amount: Money


# --- отчёт ---


class CategoryTotal(BaseModel):
    category_id: int
    category_name: str
    kind: OperationKind
    total: Money
    operations: int


class BudgetProgress(BaseModel):
    category_id: int
    category_name: str
    limit_amount: Money
    spent: Money
    left: Money
    # Процент считаем на сервере: иначе каждый клиент округлит его по-своему
    used_percent: float
    exceeded: bool


class MonthlyReport(BaseModel):
    month: Month
    income: Money
    expense: Money
    balance: Money
    by_category: list[CategoryTotal]
    budgets: list[BudgetProgress]
