"""Регистрация и вход."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AlreadyExistsError, InvalidInputError, UnauthorizedError
from app.core.security import (
    PasswordTooLongError,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.models import User


async def register(session: AsyncSession, email: str, password: str) -> tuple[User, str, int]:
    """Заводит пользователя и сразу отдаёт токен."""
    email = email.strip().lower()

    try:
        password_hash = hash_password(password)
    except PasswordTooLongError as exc:
        # Наружу это 422, а не пятисотка: пароль из 37 русских букв,
        # обычное дело, а не поломка сервиса
        raise InvalidInputError(str(exc)) from exc

    user = User(email=email, password_hash=password_hash)
    session.add(user)

    # Проверять «занята ли почта» отдельным запросом мало: две регистрации
    # с одним адресом в один момент проходят проверку обе, и вторая ловит
    # IntegrityError уже на вставке. Полагаемся на уникальный ключ в базе
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()

        raise AlreadyExistsError("такая почта уже зарегистрирована") from exc

    token, ttl = create_access_token(user.id)

    return user, token, ttl


async def login(session: AsyncSession, email: str, password: str) -> tuple[str, int]:
    """Пускает по паролю."""
    email = email.strip().lower()

    user = await session.scalar(select(User).where(User.email == email))

    # Ответ одинаков и для неизвестной почты, и для неверного пароля: иначе по
    # коду ответа можно собрать список зарегистрированных адресов
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("неверная почта или пароль")

    return create_access_token(user.id)


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)
