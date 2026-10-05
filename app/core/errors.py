"""Ошибки предметной области.

Сервисы не знают про HTTP: они бросают эти исключения, а перевод в коды ответа
лежит в одном месте, в обработчиках приложения (`app/main.py`).
"""


class DomainError(Exception):
    """Общий предок: у всех есть человеческий текст."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """Нет такой записи или она чужая, что для клиента одно и то же."""


class AlreadyExistsError(DomainError):
    """Запись с такими признаками уже есть."""


class InvalidInputError(DomainError):
    """Данные разобрались, но по смыслу не годятся."""


class UnauthorizedError(DomainError):
    """Не представился или представился неверно."""
