from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import (
    InsecureDevTokenVerifier,
    InvalidTokenError,
    build_token_verifier,
)
from app.core.config import AIMode, AuthMode, Environment, RepositoryMode, Settings, StorageMode


def _settings(**overrides: object) -> Settings:
    """検証したい項目以外はすべて妥当な値で埋める.

    こうしないと、別のバリデータが先に落ちてテストが通ってしまい、
    本来検証したいガードが壊れても気付けなくなる。
    """
    base: dict[str, object] = {
        "environment": Environment.local,
        "auth_mode": AuthMode.firebase,
        "ai_mode": AIMode.stub,
        "repository_mode": RepositoryMode.memory,
        "storage_mode": StorageMode.local,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/me").status_code == 401


def test_me_rejects_non_bearer_scheme(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_me_returns_the_authenticated_user(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer user-123"})

    assert response.status_code == 200
    assert response.json() == {"uid": "user-123", "email": None, "is_anonymous": True}


def test_insecure_verifier_rejects_blank_tokens() -> None:
    with pytest.raises(InvalidTokenError):
        InsecureDevTokenVerifier().verify("   ")


def test_insecure_dev_mode_selects_the_dev_verifier() -> None:
    settings = _settings(auth_mode=AuthMode.insecure_dev)
    assert isinstance(build_token_verifier(settings), InsecureDevTokenVerifier)


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_insecure_dev_mode_cannot_be_used_outside_local(environment: Environment) -> None:
    # 素通し認証が本番に紛れ込むのを設定段階で防げていることを保証する。
    with pytest.raises(ValidationError, match="insecure_dev"):
        _settings(
            environment=environment,
            auth_mode=AuthMode.insecure_dev,
            ai_mode=AIMode.openai,
            openai_api_key="dummy",
        )


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_stub_ai_cannot_be_used_outside_local(environment: Environment) -> None:
    # スタブは何も生成しない。本番で有効になると「生成できたが中身が偽物」になるため。
    with pytest.raises(ValidationError, match="ai_mode=stub"):
        _settings(environment=environment, ai_mode=AIMode.stub)


def test_openai_mode_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        _settings(ai_mode=AIMode.openai, openai_api_key=None)


def test_cloud_storage_requires_a_bucket() -> None:
    with pytest.raises(ValidationError, match="STORAGE_BUCKET"):
        _settings(storage_mode=StorageMode.cloud, firebase_storage_bucket=None)
