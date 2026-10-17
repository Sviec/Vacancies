"""Хеш пароля не хранит исходную строку и не принимает битую запись."""

from app.services.passwords import hash_password, verify_password


def test_roundtrip() -> None:
    stored = hash_password("password1")
    assert stored != "password1"
    assert verify_password("password1", stored)
    assert not verify_password("password2", stored)


def test_rejects_malformed_hash() -> None:
    assert not verify_password("password1", "!")
    assert not verify_password("password1", "scrypt$1$1$1$zz$aa")
