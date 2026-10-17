"""Запросы входа и регистрация."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthCredentials(BaseModel):
    """Почта и пароль для register и login."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
            msg = "invalid email"
            raise ValueError(msg)
        local, _, domain = email.partition("@")
        if not local or "." not in domain:
            msg = "invalid email"
            raise ValueError(msg)
        return email


class UserRead(BaseModel):
    """Публичные поля учётной записи. Хеш пароля наружу не отдаётся."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
