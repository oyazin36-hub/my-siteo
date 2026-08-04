from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_public_and_reports_config(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0-test"
    assert body["environment"] == "local"
    # どちらの認証方式に繋いでいるかをクライアント側で確認できることが要点。
    assert body["auth_mode"] == "insecure_dev"
