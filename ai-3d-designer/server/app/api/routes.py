"""Phase 0 のエンドポイント: 疎通確認とログイン確認."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.models.schemas import HealthResponse, MeResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """認証不要。アプリからサーバーへ到達できるかの確認に使う."""
    return HealthResponse(
        status="ok",
        version=settings.version,
        environment=settings.environment.value,
        auth_mode=settings.auth_mode.value,
    )


@router.get("/me", response_model=MeResponse, tags=["auth"])
def me(user: AuthenticatedUser = Depends(get_current_user)) -> MeResponse:
    """要認証。ログインが成立しているかの確認に使う."""
    return MeResponse(uid=user.uid, email=user.email, is_anonymous=user.is_anonymous)
