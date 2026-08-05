"""3MF の書き出し.

Bambu Studio が開ける形式で出力する。メッシュ部分は trimesh に任せ
(unit="millimeter" と実寸座標が正しく出ることを確認済み)、
その zip に 3MF 標準のメタデータを足す。

**プリンタ/フィラメントのプリセットは埋め込まない。** Bambu 独自の
project_settings.config は仕様が公開されておらず、推測で書くと
Bambu Studio がファイルごと弾く危険がある。開いた側で選ぶ運用にして、
推奨値は別途アプリに表示する。
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

_MODEL_PATH = "3D/3dmodel.model"
_NAMESPACE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


@dataclass(frozen=True)
class ThreeMfMetadata:
    title: str
    description: str = ""
    designer: str = "AI 3D Product Designer"


class ThreeMfError(Exception):
    pass


def from_mesh(mesh_stl: bytes, metadata: ThreeMfMetadata) -> bytes:
    """STL から 3MF を作る."""
    import trimesh

    try:
        mesh = trimesh.load(trimesh.util.wrap_as_stream(mesh_stl), file_type="stl", force="mesh")
        base = mesh.export(file_type="3mf")
    except Exception as exc:
        raise ThreeMfError(f"3MF を生成できませんでした: {exc}") from exc

    return _with_metadata(bytes(base), metadata)


def _with_metadata(archive: bytes, metadata: ThreeMfMetadata) -> bytes:
    """zip を組み直して 3dmodel.model にメタデータを差し込む."""
    source = zipfile.ZipFile(io.BytesIO(archive))
    model_xml = source.read(_MODEL_PATH).decode("utf-8")

    insertion = (
        f'<metadata name="Title">{_escape(metadata.title)}</metadata>'
        f'<metadata name="Designer">{_escape(metadata.designer)}</metadata>'
        f'<metadata name="Description">{_escape(metadata.description)}</metadata>'
        f'<metadata name="Application">AI 3D Product Designer</metadata>'
    )

    # <model ...> の直後に差し込む。3MF 仕様では metadata は resources より前に置く。
    marker = ">"
    open_tag_end = model_xml.index(marker, model_xml.index("<model")) + 1
    patched = model_xml[:open_tag_end] + insertion + model_xml[open_tag_end:]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        for item in source.infolist():
            payload = patched.encode("utf-8") if item.filename == _MODEL_PATH else source.read(item)
            output.writestr(item.filename, payload)

    return buffer.getvalue()


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def read_metadata(archive: bytes) -> dict[str, str]:
    """検証用。書き込んだメタデータを読み返す."""
    import re

    model_xml = zipfile.ZipFile(io.BytesIO(archive)).read(_MODEL_PATH).decode("utf-8")
    return {
        name: value
        for name, value in re.findall(r'<metadata name="([^"]+)">([^<]*)</metadata>', model_xml)
    }
