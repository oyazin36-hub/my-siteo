"""認証: Firebase ID トークンの検証.

``TokenVerifier`` を差し替え可能にしてあるので、テストとローカル開発では
Firebase なしで動かせる。本番の実装は ``FirebaseTokenVerifier`` のみ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import AuthMode, Settings


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str | None = None
    is_anonymous: bool = True


class InvalidTokenError(Exception):
    """トークンが不正、期限切れ、または署名検証に失敗した."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedUser: ...


class FirebaseTokenVerifier:
    """firebase-admin で ID トークンを検証する本番用の実装."""

    def __init__(self, credentials_path: str | None = None) -> None:
        # firebase-admin は依存が重いので遅延 import する。
        # これによりテストと insecure_dev モードでは未インストールでも動く。
        import firebase_admin
        from firebase_admin import credentials as fb_credentials

        try:
            firebase_admin.get_app()
        except ValueError:
            cred = (
                fb_credentials.Certificate(credentials_path)
                if credentials_path
                else fb_credentials.ApplicationDefault()
            )
            firebase_admin.initialize_app(cred)

    def verify(self, token: str) -> AuthenticatedUser:
        from firebase_admin import auth as fb_auth

        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception as exc:  # firebase-admin は多様な例外型を投げる
            raise InvalidTokenError(str(exc)) from exc

        provider = decoded.get("firebase", {}).get("sign_in_provider")
        return AuthenticatedUser(
            uid=decoded["uid"],
            email=decoded.get("email"),
            is_anonymous=provider == "anonymous",
        )


class InsecureDevTokenVerifier:
    """トークンをそのまま uid として扱う。ローカル開発専用。

    Firebase プロジェクトが未作成でもアプリを動かせるようにするためのもので、
    ``Settings`` 側で local 以外では選択できないよう保証している。
    """

    def verify(self, token: str) -> AuthenticatedUser:
        uid = token.strip()
        if not uid:
            raise InvalidTokenError("トークンが空です")
        return AuthenticatedUser(uid=uid, email=None, is_anonymous=True)


def build_token_verifier(settings: Settings) -> TokenVerifier:
    if settings.auth_mode is AuthMode.insecure_dev:
        return InsecureDevTokenVerifier()
    return FirebaseTokenVerifier(settings.firebase_credentials_path)


_bearer = HTTPBearer(auto_error=False)


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="認証が初期化されていません",
        )
    return verifier


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization ヘッダに Bearer トークンが必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"トークンが無効です: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
