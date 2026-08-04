from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_settings_cache() -> Iterator[None]:
    # Settings は lru_cache されるので、テスト間で環境変数の変更が効くよう毎回捨てる。
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_ENVIRONMENT", "local")
    monkeypatch.setenv("APP_AUTH_MODE", "insecure_dev")
    monkeypatch.setenv("APP_VERSION", "0.1.0-test")
    get_settings.cache_clear()

    from app.main import create_app

    # TestClient を with で使うことで lifespan が走り、token_verifier が初期化される。
    with TestClient(create_app()) as test_client:
        yield test_client
