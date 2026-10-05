"""Операции: создание, фильтры, правка, чужое."""

from __future__ import annotations

from httpx import AsyncClient


async def add(
    client: AsyncClient,
    auth: dict[str, str],
    category_id: int,
    amount: str,
    day: str,
    note: str | None = None,
) -> dict:
    payload = {"category_id": category_id, "amount": amount, "occurred_on": day}

    if note is not None:
        payload["note"] = note

    response = await client.post("/api/operations", json=payload, headers=auth)

    return response.json()


async def test_kind_comes_from_category(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    # Вид операции не спрашивается у клиента: он однозначно следует из категории
    income = await add(client, auth, categories["Зарплата"], "120000.00", "2026-09-05")
    expense = await add(client, auth, categories["Еда"], "1500.50", "2026-09-06")

    assert income["kind"] == "income"
    assert expense["kind"] == "expense"


async def test_amount_is_string_with_two_decimals(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    # Деньги уходят строкой: JSON-число с плавающей точкой округлило бы копейки
    # уже на стороне клиента
    created = await add(client, auth, categories["Еда"], "1500.50", "2026-09-06")

    assert created["amount"] == "1500.50"


async def test_rejects_non_positive_amount(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    response = await client.post(
        "/api/operations",
        json={"category_id": categories["Еда"], "amount": "-5.00", "occurred_on": "2026-09-06"},
        headers=auth,
    )

    assert response.status_code == 422


async def test_rejects_unknown_category(client: AsyncClient, auth: dict[str, str]) -> None:
    response = await client.post(
        "/api/operations",
        json={"category_id": 999999, "amount": "10.00", "occurred_on": "2026-09-06"},
        headers=auth,
    )

    assert response.status_code == 404


async def test_list_filters_and_pagination(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await add(client, auth, categories["Зарплата"], "120000.00", "2026-09-05")
    await add(client, auth, categories["Еда"], "100.00", "2026-09-06")
    await add(client, auth, categories["Еда"], "200.00", "2026-09-07")
    await add(client, auth, categories["Такси"], "300.00", "2026-08-30")

    expenses = await client.get("/api/operations?kind=expense", headers=auth)
    page = await client.get("/api/operations?kind=expense&limit=2&offset=0", headers=auth)
    september = await client.get(
        "/api/operations?date_from=2026-09-01&date_to=2026-09-30", headers=auth
    )
    food = await client.get(f"/api/operations?category_id={categories['Еда']}", headers=auth)

    assert expenses.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    # total считается по фильтру, а не по странице, иначе пагинация врёт
    assert page.json()["total"] == 3
    assert september.json()["total"] == 3
    assert food.json()["total"] == 2


async def test_list_sorted_by_date_desc(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await add(client, auth, categories["Еда"], "100.00", "2026-09-01")
    await add(client, auth, categories["Еда"], "200.00", "2026-09-10")

    items = (await client.get("/api/operations", headers=auth)).json()["items"]

    assert [item["occurred_on"] for item in items] == ["2026-09-10", "2026-09-01"]


async def test_update_changes_kind_with_category(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    operation = await add(client, auth, categories["Еда"], "100.00", "2026-09-06")

    response = await client.patch(
        f"/api/operations/{operation['id']}",
        json={"category_id": categories["Зарплата"]},
        headers=auth,
    )

    # Перенос в категорию другого вида меняет и вид самой операции
    assert response.json()["kind"] == "income"


async def test_update_keeps_note_when_not_given(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    operation = await add(client, auth, categories["Еда"], "100.00", "2026-09-06", "продукты")

    changed = await client.patch(
        f"/api/operations/{operation['id']}", json={"amount": "150.00"}, headers=auth
    )
    cleared = await client.patch(
        f"/api/operations/{operation['id']}", json={"note": None}, headers=auth
    )

    # «Поле не пришло» и «пришло пустым» это разные намерения
    assert changed.json()["note"] == "продукты"
    assert cleared.json()["note"] is None


async def test_delete(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    operation = await add(client, auth, categories["Еда"], "100.00", "2026-09-06")

    deleted = await client.delete(f"/api/operations/{operation['id']}", headers=auth)
    again = await client.delete(f"/api/operations/{operation['id']}", headers=auth)

    assert deleted.status_code == 204
    assert again.status_code == 404


async def test_foreign_operation_is_invisible(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    operation = await add(client, auth, categories["Еда"], "100.00", "2026-09-06")

    registered = await client.post(
        "/api/auth/register",
        json={"email": "сосед@example.com", "password": "чужойпароль1"},
    )
    stranger = {"Authorization": f"Bearer {registered.json()['token']['access_token']}"}

    listed = await client.get("/api/operations", headers=stranger)
    patched = await client.patch(
        f"/api/operations/{operation['id']}", json={"amount": "1.00"}, headers=stranger
    )

    assert listed.json()["total"] == 0
    assert patched.status_code == 404
