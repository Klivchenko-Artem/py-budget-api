"""Таблицы: пользователи, категории, операции, бюджеты."""

from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Общий предок таблиц."""


class OperationKind(enum.StrEnum):
    """Операция бывает только двух видов, третьего не придумано."""

    INCOME = "income"
    EXPENSE = "expense"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    categories: Mapped[list[Category]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        # Название уникально в пределах пользователя и вида: «Такси» в расходах
        # и «Такси» в доходах это разные вещи, а два расходных «Такси» уже опечатка
        UniqueConstraint("user_id", "kind", "name", name="uq_categories_user_kind_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[OperationKind] = mapped_column(
        Enum(OperationKind, name="operation_kind", values_callable=lambda e: [m.value for m in e])
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="categories")
    # passive_deletes: удалением занимается база по ondelete="CASCADE".
    # Без него SQLAlchemy сначала вытягивает все операции категории в память
    # и шлёт по DELETE на строку, на категории с тысячами трат это заметно
    operations: Mapped[list[Operation]] = relationship(
        back_populates="category", cascade="all, delete-orphan", passive_deletes=True
    )


class Operation(Base):
    """Одна трата или поступление."""

    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_operations_amount_positive"),
        # Отчёты всегда режутся по пользователю и месяцу, под это и индекс
        Index("ix_operations_user_date", "user_id", "occurred_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    # Деньги храним в Numeric, а не float: 0.1 + 0.2 в двоичной дроби не равно 0.3,
    # и на отчётах это вылезает копейками расхождения
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    kind: Mapped[OperationKind] = mapped_column(
        Enum(OperationKind, name="operation_kind", values_callable=lambda e: [m.value for m in e])
    )
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    occurred_on: Mapped[dt.date] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped[Category] = relationship(back_populates="operations")


class Budget(Base):
    """Потолок трат по категории на конкретный месяц."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "month", name="uq_budgets_user_category_month"),
        CheckConstraint("limit_amount > 0", name="ck_budgets_limit_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    # Месяц хранится первым числом: так он сравнивается и группируется как дата,
    # без разбора строк вида «2026-09»
    month: Mapped[dt.date] = mapped_column(Date)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    category: Mapped[Category] = relationship()
