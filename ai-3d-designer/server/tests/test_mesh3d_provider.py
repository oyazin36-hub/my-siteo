"""3D 生成プロバイダへの受け渡し.

Tripo に渡すのは画像の **実体** であって URL ではない。
ローカル開発では画像が /media/... というサーバー相対 URL で保存されており、
Tripo の SDK はそれを「ローカルのファイルパス」と解釈して
FileNotFoundError で落ちる。URL を渡す実装に戻さないための固定。
"""

from __future__ import annotations

import os

import pytest

from app.providers.mesh3d import GenerationRequest, Mesh3DError, TripoMeshProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class _FakeTripoClient:
    """SDK の代わり。image に何が渡ったかを見る."""

    def __init__(self) -> None:
        self.received_path: str | None = None
        self.existed: bool | None = None
        self.kwargs: dict[str, object] = {}

    async def image_to_model(self, **kwargs: object) -> str:
        self.kwargs = kwargs
        path = str(kwargs["image"])
        self.received_path = path
        # SDK は os.path.exists で実在を確かめてからアップロードする。
        # 呼び出しの最中に実在していることがすべて。
        self.existed = os.path.exists(path)
        return "task-123"

    async def close(self) -> None:  # pragma: no cover - 使わない
        pass


def _provider(client: _FakeTripoClient) -> TripoMeshProvider:
    provider = TripoMeshProvider.__new__(TripoMeshProvider)
    provider._client = client  # type: ignore[attr-defined]
    provider._model_version = None  # type: ignore[attr-defined]
    return provider


@pytest.mark.asyncio
class TestSubmit:
    async def test_hands_the_sdk_a_file_that_exists(self) -> None:
        client = _FakeTripoClient()

        job_id = await _provider(client).submit(GenerationRequest(image=PNG))

        assert job_id == "task-123"
        assert client.existed is True, "SDK が開く時点でファイルが無いと FileNotFoundError になる"
        assert client.received_path is not None
        assert client.received_path.endswith(".png")

    async def test_does_not_hand_over_a_url(self) -> None:
        client = _FakeTripoClient()
        await _provider(client).submit(GenerationRequest(image=PNG))

        assert client.received_path is not None
        # /media/... のようなサーバー相対 URL を渡してはいけない。
        assert not client.received_path.startswith("/media/")
        assert not client.received_path.startswith("http")

    async def test_cleans_up_the_temporary_file(self) -> None:
        client = _FakeTripoClient()
        await _provider(client).submit(GenerationRequest(image=PNG))

        assert client.received_path is not None
        assert not os.path.exists(client.received_path), "一時ファイルを残さない"

    async def test_uses_the_extension_of_the_media_type(self) -> None:
        client = _FakeTripoClient()
        await _provider(client).submit(GenerationRequest(image=PNG, image_media_type="image/jpeg"))

        assert client.received_path is not None
        assert client.received_path.endswith(".jpg")

    async def test_does_not_ask_for_texture_by_default(self) -> None:
        # 3Dプリント用途ではテクスチャは要らない。そのぶん安い。
        client = _FakeTripoClient()
        await _provider(client).submit(GenerationRequest(image=PNG))

        assert client.kwargs["texture"] is False
        assert client.kwargs["pbr"] is False

    async def test_wraps_sdk_failures(self) -> None:
        class _Failing(_FakeTripoClient):
            async def image_to_model(self, **kwargs: object) -> str:
                raise RuntimeError("401 Unauthorized")

        with pytest.raises(Mesh3DError) as caught:
            await _provider(_Failing()).submit(GenerationRequest(image=PNG))

        assert "401" in str(caught.value)
