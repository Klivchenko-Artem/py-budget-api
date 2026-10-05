"""Настройки сервиса. Читаются из окружения один раз за процесс."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Всё, что сервису нужно знать о внешнем мире."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://budget:budget@localhost:5432/budget"
    redis_url: str = "redis://localhost:6379/0"

    # Секрет обязателен и без значения по умолчанию: пустой секрет на проде
    # означает, что токены подделает кто угодно
    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 24 * 60

    # Отчёт за месяц пересчитывается агрегатами по всем транзакциям, поэтому
    # результат кладётся в Redis и сбрасывается при любой правке денег
    report_cache_ttl_seconds: int = 300

    app_name: str = "Учёт личных финансов"


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются лениво: так тесты успевают подменить окружение."""
    return Settings()  # type: ignore[call-arg]
