from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import AuthConfigurationError, InvalidAccessToken, decode_access_token
from app.models import User


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_csrf_token(
    request: Request,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not cookie_token or not csrf_header or not secrets.compare_digest(cookie_token, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise _unauthorized()
    try:
        payload = decode_access_token(token, settings)
    except (AuthConfigurationError, InvalidAccessToken):
        raise _unauthorized()

    if request.method not in SAFE_METHODS:
        require_csrf_token(request, request.headers.get("X-CSRF-Token"))

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

__all__ = ["CurrentUser", "get_current_user", "get_db", "require_csrf_token"]
