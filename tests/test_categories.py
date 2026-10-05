"""Категории: свои, чужие, уникальность."""

from __future__ import annotations

from httpx import AsyncClient


async def other_user_auth(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={"email": "сосед@example.com", "password": "чужойпароль1"},
    )

    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


async def test_create_category(client: AsyncClient, auth: dict[str, str]) -> None:
    response = await client.post(
        "/api/categories", json={"name": "Еда", "kind": "expense"}, headers=auth
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "expense"


async def test_same_name_in_different_kinds_allowed(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    # «Такси» в расходах и «Такси» в доходах это разные вещи, это не дубль
    first = await client.post(
        "/api/categories", json={"name": "Такси", "kind": "expense"}, headers=auth
    )
    second = await client.post(
        "/api/categories", json={"name": "Такси", "kind": "income"}, headers=auth
    )

    assert (first.status_code, second.status_code) == (201, 201)


async def test_duplicate_category_rejected(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = {"name": "Еда", "kind": "expense"}

    await client.post("/api/categories", json=payload, headers=auth)
    again = await client.post("/api/categories", json=payload, headers=auth)

    assert again.status_code == 409


async def test_list_filters_by_kind(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    response = await client.get("/api/categories?kind=expense", headers=auth)

    names = [item["name"] for item in response.json()]
    assert names == ["Еда", "Такси"]


async def test_rename(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    response = await client.patch(
        f"/api/categories/{categories['Еда']}", json={"name": "Продукты"}, headers=auth
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Продукты"


async def test_rename_into_existing_name_rejected(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    response = await client.patch(
        f"/api/categories/{categories['Еда']}", json={"name": "Такси"}, headers=auth
    )

    assert response.status_code == 409


async def test_foreign_category_answers_not_found(
    client: AsyncClient, categories: dict[str, int]
) -> None:
    stranger = await other_user_auth(client)

    # Чужая категория отвечает «не найдено», а не «нет доступа»: иначе по коду
    # ответа можно проверять, что у соседа заведено
    response = await client.patch(
        f"/api/categories/{categories['Еда']}", json={"name": "Моё"}, headers=stranger
    )

    assert response.status_code == 404


async def test_delete_removes_operations(
    client: AsyncClient, auth: dict[str, str], categories: dict[str, int]
) -> None:
    await client.post(
        "/api/operations",
        json={
            "category_id": categories["Еда"],
            "amount": "100.00",
            "occurred_on": "2026-09-05",
        },
        headers=auth,
    )

    deleted = await client.delete(f"/api/categories/{categories['Еда']}", headers=auth)
    remaining = await client.get("/api/operations", headers=auth)

    assert deleted.status_code == 204
    assert remaining.json()["total"] == 0
