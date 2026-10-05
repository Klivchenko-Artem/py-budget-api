"""Регистрация, вход, токены."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"


async def test_register_returns_token(client: AsyncClient) -> None:
    response = await client.post(
        REGISTER, json={"email": "new@example.com", "password": "паролькудлиннее"}
    )

    assert response.status_code == 201

    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["token"]["access_token"]
    assert body["token"]["expires_in"] > 0


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "паролькудлиннее"}

    await client.post(REGISTER, json=payload)
    again = await client.post(REGISTER, json=payload)

    assert again.status_code == 409


async def test_register_normalizes_email(client: AsyncClient) -> None:
    await client.post(REGISTER, json={"email": "Artem@Example.com", "password": "паролькудлиннее"})

    # Почта приводится к нижнему регистру, иначе один человек заведёт себе
    # два аккаунта, отличающихся только заглавной буквой
    response = await client.post(
        LOGIN, json={"email": "artem@example.com", "password": "паролькудлиннее"}
    )

    assert response.status_code == 200


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(REGISTER, json={"email": "short@example.com", "password": "123"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("password", "expected"),
    [("паролькудлиннее", 200), ("не тот пароль", 401), ("нет", 401)],
)
async def test_login(client: AsyncClient, token: str, password: str, expected: int) -> None:
    # Короткий неверный пароль отвечает 401, а не 422: длину на входе не
    # проверяем, чтобы не рассказывать подбирающему про нашу политику
    response = await client.post(LOGIN, json={"email": "artem@example.com", "password": password})

    assert response.status_code == expected


async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        LOGIN, json={"email": "никого@example.com", "password": "паролькудлиннее"}
    )

    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_rejects_garbage_token(client: AsyncClient) -> None:
    # Заголовки только в ASCII, поэтому «мусор» тут латиницей
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401


async def test_me_returns_owner(client: AsyncClient, auth: dict[str, str]) -> None:
    response = await client.get("/api/auth/me", headers=auth)

    assert response.status_code == 200
    assert response.json()["email"] == "artem@example.com"


async def test_long_password_is_rejected_not_crashed(client: AsyncClient) -> None:
    """bcrypt не берёт пароли длиннее 72 байт и бросает ValueError.

    Считать надо в байтах: 37 русских букв это 74 байта, то есть вполне
    обычный пароль, который раньше ронял регистрацию в пятисотку.
    """
    response = await client.post(
        REGISTER,
        json={"email": "long@example.com", "password": "ё" * 37},
    )

    assert response.status_code == 422, response.text
    assert "72" in response.json()["detail"]


async def test_password_at_the_limit_is_accepted(client: AsyncClient) -> None:
    """Ровно 72 байта: граница, которую bcrypt ещё принимает."""
    response = await client.post(
        REGISTER,
        json={"email": "limit@example.com", "password": "a" * 72},
    )

    assert response.status_code == 201, response.text


async def test_login_with_long_password_says_401(client: AsyncClient) -> None:
    """Вход с непомерным паролем это отказ, а не поломка."""
    await client.post(
        REGISTER,
        json={"email": "user@example.com", "password": "нормальный-пароль"},
    )

    response = await client.post(
        LOGIN,
        json={"email": "user@example.com", "password": "ё" * 40},
    )

    assert response.status_code == 401, response.text
