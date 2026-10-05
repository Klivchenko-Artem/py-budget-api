"""Схемы регистрации и входа."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """Регистрация: тут пароль обязан быть приличной длины."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Вход: длину пароля не проверяем.

    Требование «не короче восьми» на входе выдало бы 422 вместо 401 и заодно
    рассказало бы подбирающему пароль, какая у нас политика.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: dt.datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterResponse(BaseModel):
    user: UserRead
    token: Token
