"""Отчёт за месяц, бюджеты и кеш."""

from __future__ import annotations

import datetime as dt

from httpx import AsyncClient

from app.core import cache

REPORT = "/api/reports/monthly?month=2026-09"


async def fill(client: AsyncClient, auth: dict[str, str], categories: dict[str, int]) -> None:
    rows = [
        (categories["Зарплата"], "120000.00", "2026-09-05"),
        (categories["Еда"], "1500.50", "2026-09-06"),
        (categories["Еда"], "800.00", "2026-09-07"),
        (categories["Такси"], "450.00", "2026-09-08"),
        # Прошлый месяц в сентябрьский отчёт попасть не должен
        (categories["Еда"], "999.00", "2026-08-30"),
    ]

    for category_id, amount, day in rows:
        await client.post(
            "/api/operations",
            json={"category_id": category_id, "amount": amount, "occurred_on": day},
            headers=auth,
        )


async def test_monthly_totals(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await fill(client, auth, categories)

    report = (await client.get(REPORT, headers=auth)).json()

    assert report["month"] == "2026-09"
    assert report["income"] == "120000.00"
    assert report["expense"] == "2750.50"
    assert report["balance"] == "117249.50"

    by_name = {row["category_name"]: row for row in report["by_category"]}
    assert by_name["Еда"]["total"] == "2300.50"
    assert by_name["Еда"]["operations"] == 2
    assert "Такси" in by_name


async def test_empty_month_is_zero(client: AsyncClient, auth: dict[str, str]) -> None:
    report = (await client.get("/api/reports/monthly?month=2026-01", headers=auth)).json()

    assert report["income"] == "0.00"
    assert report["balance"] == "0.00"
    assert report["by_category"] == []


async def test_budget_progress(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await fill(client, auth, categories)

    await client.put(
        "/api/budgets",
        json={"category_id": categories["Еда"], "month": "2026-09", "limit_amount": "2000.00"},
        headers=auth,
    )
    await client.put(
        "/api/budgets",
        json={"category_id": categories["Такси"], "month": "2026-09", "limit_amount": "1000.00"},
        headers=auth,
    )

    report = (await client.get(REPORT, headers=auth)).json()
    budgets = {row["category_name"]: row for row in report["budgets"]}

    assert budgets["Еда"]["spent"] == "2300.50"
    assert budgets["Еда"]["exceeded"] is True
    # Остаток не уходит в минус: перерасход виден по флагу
    assert budgets["Еда"]["left"] == "0.00"
    assert budgets["Такси"]["left"] == "550.00"
    assert budgets["Такси"]["exceeded"] is False
    assert budgets["Такси"]["used_percent"] == 45.0


async def test_budget_only_for_expense_category(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    response = await client.put(
        "/api/budgets",
        json={"category_id": categories["Зарплата"], "month": "2026-09", "limit_amount": "10.00"},
        headers=auth,
    )

    assert response.status_code == 422


async def test_budget_is_rewritten_not_duplicated(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    payload = {"category_id": categories["Еда"], "month": "2026-09", "limit_amount": "2000.00"}

    first = await client.put("/api/budgets", json=payload, headers=auth)
    second = await client.put(
        "/api/budgets", json={**payload, "limit_amount": "3000.00"}, headers=auth
    )
    listed = (await client.get("/api/budgets?month=2026-09", headers=auth)).json()

    assert first.json()["id"] == second.json()["id"]
    assert len(listed) == 1
    assert listed[0]["limit_amount"] == "3000.00"


async def test_report_is_cached(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await fill(client, auth, categories)

    first = (await client.get(REPORT, headers=auth)).json()

    # Ключ месяца появился в Redis, а не считается заново на каждый показ
    assert await cache.get_client().exists(cache.report_key(1, dt.date(2026, 9, 1)))

    second = (await client.get(REPORT, headers=auth)).json()
    assert first == second


async def test_cache_drops_on_money_change(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await fill(client, auth, categories)

    before = (await client.get(REPORT, headers=auth)).json()

    created = await client.post(
        "/api/operations",
        json={"category_id": categories["Еда"], "amount": "1000.00", "occurred_on": "2026-09-09"},
        headers=auth,
    )
    after = (await client.get(REPORT, headers=auth)).json()

    assert before["expense"] == "2750.50"
    assert after["expense"] == "3750.50"

    await client.delete(f"/api/operations/{created.json()['id']}", headers=auth)
    restored = (await client.get(REPORT, headers=auth)).json()

    assert restored["expense"] == "2750.50"


async def test_cache_drops_when_operation_moves_month(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    created = await client.post(
        "/api/operations",
        json={"category_id": categories["Еда"], "amount": "500.00", "occurred_on": "2026-09-09"},
        headers=auth,
    )

    # Прогреваем оба месяца, потом переносим операцию из сентября в октябрь
    await client.get(REPORT, headers=auth)
    await client.get("/api/reports/monthly?month=2026-10", headers=auth)

    await client.patch(
        f"/api/operations/{created.json()['id']}",
        json={"occurred_on": "2026-10-02"},
        headers=auth,
    )

    september = (await client.get(REPORT, headers=auth)).json()
    october = (await client.get("/api/reports/monthly?month=2026-10", headers=auth)).json()

    assert september["expense"] == "0.00"
    assert october["expense"] == "500.00"


async def test_budget_change_drops_cache(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await fill(client, auth, categories)
    await client.get(REPORT, headers=auth)

    await client.put(
        "/api/budgets",
        json={"category_id": categories["Еда"], "month": "2026-09", "limit_amount": "5000.00"},
        headers=auth,
    )

    report = (await client.get(REPORT, headers=auth)).json()

    assert report["budgets"][0]["limit_amount"] == "5000.00"


async def test_broken_month_is_422_not_500(client: AsyncClient, auth: dict[str, str]) -> None:
    """Кривой месяц в строке запроса это ошибка клиента, а не поломка сервиса.

    Раньше ValueError из разбора не ловил никто, и `?month=2026-9` отдавал
    пятисотку с трейсбеком.
    """
    for month in ("2026-9", "abc", "2026-13", "2026-09-99"):
        response = await client.get(f"/api/reports/monthly?month={month}", headers=auth)

        assert response.status_code == 422, f"{month}: {response.text}"
