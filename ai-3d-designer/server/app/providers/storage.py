"""生成物の保存先.

画像生成 API が返す URL は短時間で失効するため、必ず自前で保存してから
その URL をクライアントに渡す。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol


class ImageStorage(Protocol):
    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        """保存してクライアントから参照できる URL を返す."""
        ...


class LocalImageStorage:
    """ローカルのファイルシステムに保存し、静的配信の URL を返す。開発用."""

    def __init__(self, root: Path, public_prefix: str = "/media") -> None:
        self._root = root
        self._public_prefix = public_prefix.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        extension = {"image/png": "png", "image/jpeg": "jpg"}.get(media_type, "bin")
        directory = self._root / project_id
        directory.mkdir(parents=True, exist_ok=True)

        name = f"{uuid.uuid4().hex}.{extension}"
        (directory / name).write_bytes(data)
        return f"{self._public_prefix}/{project_id}/{name}"


class CloudImageStorage:
    """Firebase Cloud Storage に保存する。本番用."""

    def __init__(self, bucket_name: str) -> None:
        from firebase_admin import storage as fb_storage

        self._bucket = fb_storage.bucket(bucket_name)

    async def put(self, *, project_id: str, data: bytes, media_type: str) -> str:
        extension = {"image/png": "png", "image/jpeg": "jpg"}.get(media_type, "bin")
        blob = self._bucket.blob(f"projects/{project_id}/{uuid.uuid4().hex}.{extension}")
        blob.upload_from_string(data, content_type=media_type)
        return f"gs://{self._bucket.name}/{blob.name}"
