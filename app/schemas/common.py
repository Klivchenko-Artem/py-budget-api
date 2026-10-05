"""Типы, которые повторяются в нескольких схемах."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, PlainSerializer

# Деньги: до 10 знаков до запятой и ровно два после. Наружу отдаём строкой,
# JSON-число с плавающей точкой округлило бы копейки на стороне клиента
Money = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2),
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str),
]

PositiveMoney = Annotated[
    Decimal,
    Field(gt=0, max_digits=12, decimal_places=2),
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str),
]


def to_first_day(value: object) -> object:
    """Принимает и «2026-09», и полную дату, приводит к первому числу месяца."""
    if isinstance(value, str) and len(value) == 7 and value[4] == "-":
        value = f"{value}-01"

    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value)
        except ValueError:
            return value

    if isinstance(value, dt.datetime):
        value = value.date()

    if isinstance(value, dt.date):
        return value.replace(day=1)

    return value


# Месяц всегда хранится и сравнивается как первое число: так его можно
# сортировать и класть в индекс, не разбирая строку «2026-09» каждый раз
Month = Annotated[
    dt.date,
    BeforeValidator(to_first_day),
    PlainSerializer(lambda value: value.strftime("%Y-%m"), return_type=str),
]
