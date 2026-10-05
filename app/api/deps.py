"""Зависимости запроса: сессия базы и текущий пользователь."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, parse_access_token
from app.db.session import session_scope

SessionDep = Annotated[AsyncSession, Depends(session_scope)]

# auto_error=False: без заголовка хотим свой текст ошибки, а не чужой
_bearer = HTTPBearer(auto_error=False, description="Токен из /api/auth/login")


async def current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> int:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="нужен заголовок Authorization: Bearer <токен>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return parse_access_token(credentials.credentials)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="токен недействителен",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


CurrentUser = Annotated[int, Depends(current_user_id)]
