from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import Settings, get_settings


password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))


class AuthConfigurationError(Exception):
    pass


class InvalidAccessToken(Exception):
    pass


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(password, hashed_password)
    except Exception:
        return False


def verify_password_against_dummy(password: str) -> bool:
    return verify_password(password, dummy_password_hash)


def create_access_token(user_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.jwt_secret_key:
        raise AuthConfigurationError("JWT_SECRET_KEY is not configured.")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.jwt_secret_key:
        raise AuthConfigurationError("JWT_SECRET_KEY is not configured.")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iss", "iat", "exp", "jti", "type"]},
        )
    except InvalidTokenError as exc:
        raise InvalidAccessToken from exc
    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise InvalidAccessToken
    return payload

