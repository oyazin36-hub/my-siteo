"""画像生成プロバイダ."""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedImageData:
    data: bytes
    media_type: str


class ImageGenerationError(Exception):
    pass


class ImageProvider(Protocol):
    async def generate(self, prompt: str) -> GeneratedImageData: ...


class OpenAIImageProvider:
    """OpenAI の画像生成.

    URL ではなく base64 で受け取る。API が返す URL は短時間で失効するため、
    こちら側で保存しないと画像が後から見られなくなる。
    """

    def __init__(self, api_key: str, model: str = "gpt-image-1", size: str = "1024x1024") -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._size = size

    async def generate(self, prompt: str) -> GeneratedImageData:
        try:
            result = await self._client.images.generate(
                model=self._model,
                prompt=prompt,
                size=self._size,
                n=1,
            )
        except Exception as exc:
            raise ImageGenerationError(f"画像の生成に失敗しました: {exc}") from exc

        if not result.data or result.data[0].b64_json is None:
            raise ImageGenerationError("画像データが返されませんでした")

        return GeneratedImageData(
            data=base64.b64decode(result.data[0].b64_json),
            media_type="image/png",
        )


class StubImageProvider:
    """API キーなしで開発・テストするためのスタブ.

    プロンプトから決まる色の単色 PNG を生成する。実画像の代わりではなく、
    保存・配信・表示までの経路を通すための足場。
    """

    async def generate(self, prompt: str) -> GeneratedImageData:
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        rgb = (digest[0], digest[1], digest[2])
        return GeneratedImageData(data=_solid_png(rgb), media_type="image/png")


def _solid_png(rgb: tuple[int, int, int], size: int = 64) -> bytes:
    """依存を増やさずに単色 PNG を組み立てる(Pillow を入れないため)."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8bit truecolor
    row = b"\x00" + bytes(rgb) * size  # 各行の先頭はフィルタ種別
    raw = row * size

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
