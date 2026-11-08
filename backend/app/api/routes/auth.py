from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_csrf_token
from app.core.config import get_settings
from app.core.security import AuthConfigurationError, create_access_token, hash_password, verify_password, verify_password_against_dummy
from app.models import User
from app.schemas import CsrfResponse, UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_auth_configured() -> None:
    if not get_settings().jwt_secret_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured on the server.")


def _set_session_cookies(response: Response, user: User) -> None:
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    try:
        access_token = create_access_token(user.id, settings)
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured on the server.") from exc
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(key=settings.auth_cookie_name, value=access_token, max_age=settings.access_token_expire_minutes * 60, httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite, path="/")
    response.set_cookie(key=settings.csrf_cookie_name, value=csrf_token, max_age=settings.access_token_expire_minutes * 60, httponly=False, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite, path="/")


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/csrf", response_model=CsrfResponse)
def csrf(response: Response) -> CsrfResponse:
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(key=settings.csrf_cookie_name, value=secrets.token_urlsafe(32), httponly=False, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite, path="/")
    return CsrfResponse()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, response: Response, db: Session = Depends(get_db), _: None = Depends(require_csrf_token)) -> UserResponse:
    _require_auth_configured()
    existing = db.scalar(select(User).where(func.lower(User.email) == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=payload.email, display_name=payload.display_name, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    db.refresh(user)
    _set_session_cookies(response, user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db), _: None = Depends(require_csrf_token)) -> UserResponse:
    _require_auth_configured()
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email))
    if user:
        password_valid = verify_password(payload.password, user.password_hash)
    else:
        password_valid = verify_password_against_dummy(payload.password)
    valid = bool(user and user.is_active and password_valid)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _set_session_cookies(response, user)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/logout", response_model=CsrfResponse)
def logout(response: Response, _: None = Depends(require_csrf_token)) -> CsrfResponse:
    _clear_session_cookies(response)
    return CsrfResponse()

