"""STEP4(3Dモデル生成)の通しテスト.

Phase 2 の完了条件「画像から3Dモデルが生成され、STL が取得できる」を検証する。
"""

from __future__ import annotations

import io
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import requires_openscad

AUTH = {"Authorization": "Bearer test-user"}
OTHER_AUTH = {"Authorization": "Bearer someone-else"}

MEISHI = "名刺入れをつくって。ボタンで取り出せて、30枚入って、ポケットに入るサイズ"
NEKO = "猫の置物をつくって"


def _through_images(client: TestClient, text: str = MEISHI) -> dict[str, Any]:
    """STEP1〜3 を通して画像確認まで進んだプロジェクトを作る."""
    project = client.post("/projects", json={"text": text}, headers=AUTH).json()
    client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
    return client.post(f"/projects/{project['id']}/images", headers=AUTH).json()


class TestStep4:
    def test_generates_a_printable_stl(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)

        response = client.post(f"/projects/{project['id']}/model", headers=AUTH)
        assert response.status_code == 202, response.text

        final = client.get(f"/projects/{project['id']}", headers=AUTH).json()
        model = final["model"]

        assert model["job_status"] == "done"
        assert final["status"] == "model_review"
        assert model["format"] == "stl"
        assert model["watertight"] is True
        assert model["printable"] is True
        assert model["face_count"] > 0

    def test_the_stl_is_stored_and_downloadable(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)

        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]

        # 生成 API が返す期限付き URL ではなく、自前で保存した URL であること。
        assert model["url"].startswith("/media/")
        assert model["url"].endswith(".stl")

        served = client.get(model["url"])
        assert served.status_code == 200
        assert len(served.content) > 84  # STL ヘッダより大きい

    def test_the_response_is_immediate_and_reports_progress(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)

        # 受け付けの時点で状態が分かること(数分待たされる処理なので)。
        accepted = client.post(f"/projects/{project['id']}/model", headers=AUTH).json()
        assert accepted["model"]["job_status"] in {"queued", "running", "done"}
        assert accepted["status"] == "model_generating"

    def test_records_which_pipeline_produced_it(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)

        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]
        assert model["gen_source"] == "stub"
        # 画像から起こしたモデルは寸法を保証しない。
        assert model["dimensional_accuracy"] == "approximate"

    def test_cannot_generate_before_images_exist(self, client: TestClient) -> None:
        project = client.post("/projects", json={"text": NEKO}, headers=AUTH).json()
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)

        response = client.post(f"/projects/{project['id']}/model", headers=AUTH)
        assert response.status_code == 409

    def test_other_users_cannot_generate(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        response = client.post(f"/projects/{project['id']}/model", headers=OTHER_AUTH)
        assert response.status_code == 404


# 機構ルートを通るので OpenSCAD が要る。
@requires_openscad
class TestRoutesDifferInGuarantee:
    """装飾ルートと機構ルートで寸法の扱いが違うことを保証する.

    Phase 3 で機構ルートは CAD 経路に変わり、寸法保証がつくようになった。
    装飾ルートは従来どおり画像経路で、寸法は保証しない。
    """

    def test_mechanism_route_guarantees_dimensions(self, client: TestClient) -> None:
        project = _through_images(client, MEISHI)
        assert project["route"] == "mechanism"

        client.post(f"/projects/{project['id']}/model", headers=AUTH)
        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]

        assert model["dimensional_accuracy"] == "guaranteed"
        assert model["gen_source"] == "parametric"
        # 寸法が合っているので、食い違いも暫定の断りも出ない。
        assert not any("食い違" in w for w in model["warnings"])
        assert not any("暫定形状" in w for w in model["warnings"])

    def test_decorative_route_does_not_guarantee_dimensions(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        assert project["route"] == "decorative"

        client.post(f"/projects/{project['id']}/model", headers=AUTH)
        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]

        assert model["dimensional_accuracy"] == "approximate"
        assert model["gen_source"] == "stub"  # 画像経路(Tripo の代わり)


class TestRevision:
    def test_regenerates_and_records_the_request(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)

        response = client.post(
            f"/projects/{project['id']}/model/revise",
            json={"request": "もっと丸みをつけて"},
            headers=AUTH,
        )
        assert response.status_code == 202, response.text

        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]
        assert model["job_status"] == "done"
        assert [r["request"] for r in model["revisions"]] == ["もっと丸みをつけて"]

    def test_cannot_revise_before_a_model_exists(self, client: TestClient) -> None:
        project = _through_images(client, NEKO)
        response = client.post(
            f"/projects/{project['id']}/model/revise",
            json={"request": "丸く"},
            headers=AUTH,
        )
        assert response.status_code == 409


class TestUploads:
    def test_accepts_a_png_and_returns_a_usable_url(self, client: TestClient) -> None:
        from app.providers.imagegen import _solid_png

        response = client.post(
            "/projects/uploads",
            files={"file": ("ref.png", io.BytesIO(_solid_png((10, 20, 30))), "image/png")},
            headers=AUTH,
        )
        assert response.status_code == 201, response.text
        url = response.json()["url"]

        # 返った URL がそのまま参照できること。
        assert client.get(url).status_code == 200

        # そのままアイデアに添付できること。
        created = client.post("/projects", json={"text": NEKO, "image_urls": [url]}, headers=AUTH)
        assert created.status_code == 201
        assert created.json()["idea"]["image_urls"] == [url]

    def test_rejects_a_non_image(self, client: TestClient) -> None:
        response = client.post(
            "/projects/uploads",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            headers=AUTH,
        )
        assert response.status_code == 415

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(
            "/projects/uploads",
            files={"file": ("ref.png", io.BytesIO(b"x"), "image/png")},
        )
        assert response.status_code == 401


class TestPreviewModel:
    def test_provides_a_glb_for_the_viewer(self, client: TestClient) -> None:
        # 3Dビューアは STL を扱えないため、印刷用とは別に表示用 GLB を持つ。
        project = _through_images(client, NEKO)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)

        model = client.get(f"/projects/{project['id']}", headers=AUTH).json()["model"]

        assert model["url"].endswith(".stl")
        assert model["preview_url"].endswith(".glb")
        assert model["preview_url"] != model["url"]

        served = client.get(model["preview_url"])
        assert served.status_code == 200
        assert served.content[:4] == b"glTF"  # GLB のマジックナンバー
