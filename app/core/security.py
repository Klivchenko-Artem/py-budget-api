"""Пароли и токены доступа."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


class TokenError(Exception):
    """Токен не разобрался: протух, подписан не тем ключом или сломан."""


#: bcrypt длиннее 72 байт не берёт и с версии 5.0 бросает ValueError, а не
#: режет молча. Считаем в байтах, а не в символах: 37 русских букв это уже
#: 74 байта, и такой пароль роняет регистрацию в пятисотку.
MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Пароль не влезает в bcrypt."""


def hash_password(password: str) -> str:
    """Хеширует пароль bcrypt'ом. Соль bcrypt хранит внутри самого хеша."""
    encoded = password.encode()

    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(f"пароль длиннее {MAX_PASSWORD_BYTES} байт")

    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Сверяет пароль с хешем."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        # Битый хеш в базе это не «пароль подошёл»
        return False


def create_access_token(user_id: int) -> tuple[str, int]:
    """Выдаёт токен доступа и его срок жизни в секундах."""
    settings = get_settings()
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + ttl,
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return token, int(ttl.total_seconds())


def parse_access_token(token: str) -> int:
    """Достаёт идентификатор пользователя из токена."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    subject = payload.get("sub")
    if subject is None:
        raise TokenError("в токене нет владельца")

    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise TokenError("владелец токена не похож на идентификатор") from exc
