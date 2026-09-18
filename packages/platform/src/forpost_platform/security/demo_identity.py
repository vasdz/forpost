"""Короткоживущие HMAC-утверждения для явно включённого demo-контура."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Final

from pydantic import ValidationError

from .identity import SecuritySubject

AUDIENCE: Final[str] = "forpost-api"
MAX_TOKEN_CHARS: Final[int] = 4096
MAX_TTL_SECONDS: Final[int] = 300
MIN_SECRET_CHARS: Final[int] = 32


class DemoIdentityError(ValueError):
    """Demo-утверждение не прошло безопасную проверку."""


def issue_demo_assertion(
    subject: SecuritySubject,
    secret: str,
    *,
    now: datetime | None = None,
    ttl_seconds: int = MAX_TTL_SECONDS,
) -> str:
    """Подписывает минимальный серверный контекст без сторонней JWT-библиотеки."""
    _validate_secret(secret)
    if not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise DemoIdentityError("Срок demo-утверждения недействителен")
    issued_at = _utc_now(now)
    payload = {
        "aud": AUDIENCE,
        "complexes": sorted(subject.allowed_complexes),
        "districts": sorted(subject.allowed_districts),
        "exp": int(issued_at.timestamp()) + ttl_seconds,
        "iat": int(issued_at.timestamp()),
        "jti": secrets.token_hex(16),
        "roles": sorted(role.value for role in subject.roles),
        "sub": subject.user_id,
        "username": subject.username,
    }
    encoded_payload = _encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256)
    return f"{encoded_payload}.{_encode(signature.digest())}"


def verify_demo_assertion(
    token: str,
    secret: str,
    *,
    now: datetime | None = None,
    audience: str = AUDIENCE,
) -> SecuritySubject:
    """Проверяет подпись, аудиторию, время и строгую схему субъекта."""
    _validate_secret(secret)
    if not token or len(token) > MAX_TOKEN_CHARS or token.count(".") != 1:
        raise DemoIdentityError("Demo-утверждение недействительно")
    encoded_payload, encoded_signature = token.split(".", maxsplit=1)
    expected = hmac.new(
        secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        presented = _decode(encoded_signature)
    except (ValueError, UnicodeError) as error:
        raise DemoIdentityError("Demo-утверждение недействительно") from error
    if not hmac.compare_digest(presented, expected):
        raise DemoIdentityError("Demo-утверждение недействительно")

    try:
        payload = json.loads(_decode(encoded_payload))
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise DemoIdentityError("Demo-утверждение недействительно") from error
    required = {
        "aud",
        "complexes",
        "districts",
        "exp",
        "iat",
        "jti",
        "roles",
        "sub",
        "username",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise DemoIdentityError("Demo-утверждение недействительно")
    if payload["aud"] != audience:
        raise DemoIdentityError("Недопустимая аудитория demo-утверждения")

    current = int(_utc_now(now).timestamp())
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        raise DemoIdentityError("Demo-утверждение недействительно")
    if payload["exp"] <= current:
        raise DemoIdentityError("Demo-утверждение истекло")
    if payload["iat"] > current + 30 or payload["exp"] - payload["iat"] > MAX_TTL_SECONDS:
        raise DemoIdentityError("Срок demo-утверждения недействителен")

    try:
        return SecuritySubject.model_validate(
            {
                "user_id": payload["sub"],
                "username": payload["username"],
                "roles": payload["roles"],
                "allowed_districts": payload["districts"],
                "allowed_complexes": payload["complexes"],
            }
        )
    except ValidationError as error:
        raise DemoIdentityError("Demo-утверждение недействительно") from error


def _validate_secret(secret: str) -> None:
    if len(secret) < MIN_SECRET_CHARS:
        raise DemoIdentityError("Секрет demo-контура слишком короткий")


def _utc_now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        raise DemoIdentityError("Время demo-утверждения должно содержать часовой пояс")
    return result.astimezone(UTC)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if not value or any(character not in allowed for character in value):
        raise ValueError("invalid base64url")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)
