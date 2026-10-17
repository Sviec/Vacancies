"""Хеш пароля через stdlib scrypt. Отдельной криптобиблиотеки нет."""

import hashlib
import hmac
import secrets

_N = 2**14
_R = 8
_P = 1
_SALT_BYTES = 16
_DKLEN = 32


def hash_password(password: str) -> str:
    """Вернуть строку `scrypt$n$r$p$salt$hash`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Сверить пароль. Битая запись и неверный пароль дают False."""
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected = bytes.fromhex(parts[5])
    except ValueError:
        return False
    if n < 2 or r < 1 or p < 1 or not salt or not expected:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(digest, expected)
