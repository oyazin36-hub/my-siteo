"""STEP1〜3 の通しテスト.

Phase 1 の完了条件「名刺入れを作ってと入力すると企画書と画像が出て、
修正指示が反映される」を API 経由で検証する。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-user"}
OTHER_AUTH = {"Authorization": "Bearer someone-else"}

MEISHI_IDEA = (
    "名刺入れをつくって。普段見えてるのは添付画像。"
    "だけどボタンを押したら名刺が取り出しやすい様に取り出せる。"
    "名刺は30枚くらい入ればいいかな。ポケットに収納しやすい大きさで作ってね"
)


def _create(client: TestClient, text: str = MEISHI_IDEA, **kwargs: Any) -> dict[str, Any]:
    response = client.post("/projects", json={"text": text, **kwargs}, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


class TestStep1:
    def test_creates_a_project_in_idea_input(self, client: TestClient) -> None:
        project = _create(client)

        assert project["status"] == "idea_input"
        assert project["owner_uid"] == "test-user"
        assert project["proposal"] is None
        assert project["idea"]["text"] == MEISHI_IDEA

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.post("/projects", json={"text": "何か"}).status_code == 401

    def test_rejects_empty_idea(self, client: TestClient) -> None:
        response = client.post("/projects", json={"text": ""}, headers=AUTH)
        assert response.status_code == 422


class TestStep2Proposal:
    def test_generates_a_proposal_from_the_idea(self, client: TestClient) -> None:
        project = _create(client)

        response = client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "proposal_review"
        # 寸法制約を含む要望なので機構ルートに振り分けられること。
        assert body["route"] == "mechanism"

        proposal = body["proposal"]
        assert proposal["product_name"]
        assert proposal["capacity"] == "名刺30枚"
        assert proposal["print_time_est_min"] > 0
        # ポケットに入る大きさという指示が寸法に効いていること。
        assert proposal["size_mm"]["width"] <= 100
        assert proposal["size_mm"]["height"] <= 20
        # タイトルが商品名で更新されること。
        assert body["title"] == proposal["product_name"]

    def test_cannot_generate_twice(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)

        again = client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        assert again.status_code == 409

    def test_revision_is_applied_and_recorded(self, client: TestClient) -> None:
        project = _create(client)
        before = client.post(f"/projects/{project['id']}/proposal", headers=AUTH).json()
        original_height = before["proposal"]["size_mm"]["height"]

        response = client.post(
            f"/projects/{project['id']}/proposal/revise",
            json={"request": "もう少し薄くして"},
            headers=AUTH,
        )
        assert response.status_code == 200, response.text
        after = response.json()

        assert after["proposal"]["size_mm"]["height"] < original_height
        assert after["status"] == "proposal_review"
        revisions = after["proposal"]["revisions"]
        assert len(revisions) == 1
        assert revisions[0]["request"] == "もう少し薄くして"

    def test_revision_history_accumulates(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)

        for request in ("もう少し薄くして", "少し小さくして"):
            client.post(
                f"/projects/{project['id']}/proposal/revise",
                json={"request": request},
                headers=AUTH,
            )

        final = client.get(f"/projects/{project['id']}", headers=AUTH).json()
        # 企画が差し替わっても履歴が消えないこと。
        assert [r["request"] for r in final["proposal"]["revisions"]] == [
            "もう少し薄くして",
            "少し小さくして",
        ]

    def test_cannot_revise_before_a_proposal_exists(self, client: TestClient) -> None:
        project = _create(client)
        response = client.post(
            f"/projects/{project['id']}/proposal/revise",
            json={"request": "薄くして"},
            headers=AUTH,
        )
        assert response.status_code == 409


class TestStep3Images:
    def test_generates_the_five_image_kinds(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)

        response = client.post(f"/projects/{project['id']}/images", headers=AUTH)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "image_review"
        assert [image["kind"] for image in body["images"]] == [
            "exterior",
            "scene",
            "exploded",
            "internal",
            "dimensions",
        ]

    def test_stores_images_and_serves_them(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        body = client.post(f"/projects/{project['id']}/images", headers=AUTH).json()

        url = body["images"][0]["url"]
        # 生成 API が返す期限付き URL ではなく、自前で保存した URL であること。
        assert url.startswith("/media/")

        served = client.get(url)
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/png")

    def test_prompt_forces_single_object_on_plain_background(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        body = client.post(f"/projects/{project['id']}/images", headers=AUTH).json()

        exterior = next(i for i in body["images"] if i["kind"] == "exterior")
        # 後段の画像→3D生成の品質はここで決まるので、固定文言が入っていることを保証する。
        assert "背景は無地の白" in exterior["prompt"]
        assert "被写体は1点のみ" in exterior["prompt"]

    def test_cannot_generate_images_before_a_proposal(self, client: TestClient) -> None:
        project = _create(client)
        response = client.post(f"/projects/{project['id']}/images", headers=AUTH)
        assert response.status_code == 409

    def test_revision_regenerates_and_records(self, client: TestClient) -> None:
        project = _create(client)
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        before = client.post(f"/projects/{project['id']}/images", headers=AUTH).json()

        response = client.post(
            f"/projects/{project['id']}/images/revise",
            json={"request": "もっと明るい色で"},
            headers=AUTH,
        )
        assert response.status_code == 200, response.text
        after = response.json()

        assert after["status"] == "image_review"
        assert after["image_revisions"][0]["request"] == "もっと明るい色で"
        # 画像が作り直されていること(プロンプトに指示が反映されている)。
        assert "もっと明るい色で" in after["images"][0]["prompt"]
        assert after["images"][0]["url"] != before["images"][0]["url"]


class TestOwnership:
    def test_other_users_cannot_read_the_project(self, client: TestClient) -> None:
        project = _create(client)

        response = client.get(f"/projects/{project['id']}", headers=OTHER_AUTH)
        # 存在自体を伏せるため 403 ではなく 404 を返す。
        assert response.status_code == 404

    def test_other_users_cannot_drive_the_flow(self, client: TestClient) -> None:
        project = _create(client)
        response = client.post(f"/projects/{project['id']}/proposal", headers=OTHER_AUTH)
        assert response.status_code == 404

    def test_listing_only_returns_own_projects(self, client: TestClient) -> None:
        _create(client)
        _create(client, text="猫の置物をつくって")

        mine = client.get("/projects", headers=AUTH).json()
        theirs = client.get("/projects", headers=OTHER_AUTH).json()

        assert len(mine) == 2
        assert theirs == []


class TestRouteClassification:
    @pytest.mark.parametrize(
        ("idea", "expected"),
        [
            ("名刺入れをつくって。30枚入るサイズで", "mechanism"),
            ("スマホスタンドをつくって", "mechanism"),
            ("猫の置物をつくって", "decorative"),
            # 寸法の語を含んでいても、見た目が主目的なら装飾ルートに倒す。
            ("猫の置物をつくって。手のひらサイズで", "decorative"),
            # 「画像」に含まれる「像」を装飾の合図と誤読しないこと。
            ("名刺入れをつくって。添付画像を参考に。30枚入る", "mechanism"),
        ],
    )
    def test_classifies_the_generation_route(
        self, client: TestClient, idea: str, expected: str
    ) -> None:
        project = _create(client, text=idea)
        body = client.post(f"/projects/{project['id']}/proposal", headers=AUTH).json()
        assert body["route"] == expected
