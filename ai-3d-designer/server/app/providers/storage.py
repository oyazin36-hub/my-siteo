"""生成物(画像・3Dモデル)の保存先.

外部の生成 API が返す URL は短時間で失効する(画像生成も Tripo3D も同様)ため、
必ず自前で保存してからその URL をクライアントに渡す。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

#: MIME タイプ → 拡張子。静的配信時に正しく解釈させるために必要。
_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "model/stl": "stl",
    "model/3mf": "3mf",
    "model/gltf-binary": "glb",
}


class BlobNotFoundError(Exception):
    pass


class BlobStorage(Protocol):
    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        """保存してクライアントから参照できる URL を返す."""
        ...

    async def get(self, url: str) -> bytes:
        """put() が返した URL の中身を読み戻す。見つからなければ BlobNotFoundError."""
        ...


class LocalBlobStorage:
    """ローカルのファイルシステムに保存し、静的配信の URL を返す。開発用."""

    def __init__(self, root: Path, public_prefix: str = "/media") -> None:
        self._root = root
        self._public_prefix = public_prefix.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        extension = _EXTENSIONS.get(media_type, "bin")
        directory = self._root / project_id
        directory.mkdir(parents=True, exist_ok=True)

        name = f"{uuid.uuid4().hex}.{extension}"
        (directory / name).write_bytes(data)
        return f"{self._public_prefix}/{project_id}/{name}"

    async def get(self, url: str) -> bytes:
        relative = url.removeprefix(f"{self._public_prefix}/")
        if relative == url:  # 想定した接頭辞で始まっていない
            raise BlobNotFoundError(f"扱えない URL です: {url}")

        # ".." などで保存領域の外へ出られないようにする。
        target = (self._root / relative).resolve()
        if not target.is_relative_to(self._root.resolve()):
            raise BlobNotFoundError(f"保存領域の外を指しています: {url}")
        if not target.exists():
            raise BlobNotFoundError(f"見つかりません: {url}")
        return target.read_bytes()


class CloudBlobStorage:
    """Firebase Cloud Storage に保存する。本番用."""

    def __init__(self, bucket_name: str) -> None:
        from firebase_admin import storage as fb_storage

        self._bucket = fb_storage.bucket(bucket_name)

    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        extension = _EXTENSIONS.get(media_type, "bin")
        blob = self._bucket.blob(f"projects/{project_id}/{uuid.uuid4().hex}.{extension}")
        blob.upload_from_string(data, content_type=media_type)
        return f"gs://{self._bucket.name}/{blob.name}"

    async def get(self, url: str) -> bytes:
        prefix = f"gs://{self._bucket.name}/"
        if not url.startswith(prefix):
            raise BlobNotFoundError(f"扱えない URL です: {url}")
        blob = self._bucket.blob(url.removeprefix(prefix))
        if not blob.exists():
            raise BlobNotFoundError(f"見つかりません: {url}")
        return bytes(blob.download_as_bytes())
