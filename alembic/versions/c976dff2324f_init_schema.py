"""Начальная схема: пользователи, категории, операции, бюджеты

Revision ID: c976dff2324f
Revises:
Create Date: 2026-09-09 10:09:42.908768
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c976dff2324f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.Enum("income", "expense", name="operation_kind"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "name", name="uq_categories_user_kind_name"),
    )
    op.create_index(op.f("ix_categories_user_id"), "categories", ["user_id"], unique=False)
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("limit_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint("limit_amount > 0", name="ck_budgets_limit_positive"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "category_id", "month", name="uq_budgets_user_category_month"
        ),
    )
    op.create_index(op.f("ix_budgets_category_id"), "budgets", ["category_id"], unique=False)
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"], unique=False)
    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("kind", sa.Enum("income", "expense", name="operation_kind"), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name="ck_operations_amount_positive"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_operations_category_id"), "operations", ["category_id"], unique=False)
    op.create_index(
        "ix_operations_user_date", "operations", ["user_id", "occurred_on"], unique=False
    )
    op.create_index(op.f("ix_operations_user_id"), "operations", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_operations_user_id"), table_name="operations")
    op.drop_index("ix_operations_user_date", table_name="operations")
    op.drop_index(op.f("ix_operations_category_id"), table_name="operations")
    op.drop_table("operations")
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_index(op.f("ix_budgets_category_id"), table_name="budgets")
    op.drop_table("budgets")
    op.drop_index(op.f("ix_categories_user_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    # Postgres не удаляет пользовательский тип вместе с таблицами: без этой
    # строки повторный upgrade падает с «type operation_kind already exists»
    sa.Enum(name="operation_kind").drop(op.get_bind(), checkfirst=True)
