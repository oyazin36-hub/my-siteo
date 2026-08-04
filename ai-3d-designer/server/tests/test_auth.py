from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import (
    InsecureDevTokenVerifier,
    InvalidTokenError,
    build_token_verifier,
)
from app.core.config import AuthMode, Environment, Settings


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
    settings = Settings(environment=Environment.local, auth_mode=AuthMode.insecure_dev)
    assert isinstance(build_token_verifier(settings), InsecureDevTokenVerifier)


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_insecure_dev_mode_cannot_be_used_outside_local(environment: Environment) -> None:
    # 素通し認証が本番に紛れ込むのを設定段階で防げていることを保証する。
    with pytest.raises(ValidationError):
        Settings(environment=environment, auth_mode=AuthMode.insecure_dev)
