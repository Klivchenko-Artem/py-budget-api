"""Регистрация и вход."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import NotFoundError
from app.schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, Token, UserRead
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["Вход"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
)
async def register(payload: RegisterRequest, session: SessionDep) -> RegisterResponse:
    user, token, ttl = await auth.register(session, payload.email, payload.password)

    return RegisterResponse(
        user=UserRead.model_validate(user),
        token=Token(access_token=token, expires_in=ttl),
    )


@router.post("/login", response_model=Token, summary="Вход")
async def login(payload: LoginRequest, session: SessionDep) -> Token:
    token, ttl = await auth.login(session, payload.email, payload.password)

    return Token(access_token=token, expires_in=ttl)


@router.get("/me", response_model=UserRead, summary="Кто я")
async def me(session: SessionDep, user_id: CurrentUser) -> UserRead:
    user = await auth.get_user(session, user_id)

    # Токен ещё живой, а пользователя уже нет, например, его удалили
    if user is None:
        raise NotFoundError("пользователь не найден")

    return UserRead.model_validate(user)
