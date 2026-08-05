"""3D 生成プロバイダ.

DESIGN.md §2-1 の方針どおり、プロバイダ固有のコードはこのファイルだけに閉じ込める。
他社へ乗り換える場合の変更範囲をここ1枚に限定するため、
バックエンドの他のどこにも Tripo という語を出さない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

MeshFormat = Literal["glb", "gltf", "obj", "stl", "3mf"]
JobState = Literal["queued", "running", "done", "error"]


@dataclass(frozen=True)
class GenerationRequest:
    """画像 1 枚から 3D モデルを起こす依頼."""

    image_url: str
    """STEP3 で承認された画像。プロバイダから到達できる URL である必要がある。"""

    with_texture: bool = False
    """3D プリント用途ではテクスチャを使わないので既定で False(そのぶん安価)。"""

    target_polycount: int | None = None


@dataclass(frozen=True)
class MeshArtifact:
    data: bytes
    format: MeshFormat


class Mesh3DError(Exception):
    pass


class Mesh3DProvider(Protocol):
    async def submit(self, request: GenerationRequest) -> str:
        """ジョブを投入して job_id を返す."""
        ...

    async def poll(self, job_id: str) -> JobState: ...

    async def fetch(self, job_id: str) -> MeshArtifact:
        """完了したジョブの成果物を取得する."""
        ...


class TripoMeshProvider:
    """Tripo3D 実装。公式 SDK (tripo3d) を使う.

    生成された 3D モデルの URL は短時間(数分)で失効するため、
    fetch() で必ずその場でダウンロードして bytes を返す。
    URL をそのまま保存すると、後から開けないデータが残る。
    """

    def __init__(self, api_key: str, model_version: str | None = None) -> None:
        # tripo3d と httpx は遅延 import。スタブ利用時は未インストールでも動く。
        from tripo3d import TripoClient

        self._client = TripoClient(api_key=api_key)
        self._model_version = model_version

    async def submit(self, request: GenerationRequest) -> str:
        kwargs: dict[str, object] = {
            "image": request.image_url,
            "texture": request.with_texture,
            "pbr": request.with_texture,
        }
        if self._model_version:
            kwargs["model_version"] = self._model_version
        if request.target_polycount is not None:
            kwargs["face_limit"] = request.target_polycount

        try:
            return await self._client.image_to_model(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            raise Mesh3DError(f"3Dモデルの生成依頼に失敗しました: {exc}") from exc

    async def poll(self, job_id: str) -> JobState:
        from tripo3d import TaskStatus

        try:
            task = await self._client.get_task(job_id)
        except Exception as exc:
            raise Mesh3DError(f"3Dモデルの生成状況を取得できませんでした: {exc}") from exc

        match task.status:
            case TaskStatus.QUEUED:
                return "queued"
            case TaskStatus.RUNNING:
                return "running"
            case TaskStatus.SUCCESS:
                return "done"
            case _:
                # failed / cancelled / banned / expired / unknown はすべて失敗扱い。
                # 理由が分かる場合はメッセージに含める。
                reason = task.error_msg or task.status.value
                raise Mesh3DError(f"3Dモデルの生成に失敗しました: {reason}")

    async def fetch(self, job_id: str) -> MeshArtifact:
        import httpx

        try:
            task = await self._client.get_task(job_id)
        except Exception as exc:
            raise Mesh3DError(f"3Dモデルの取得に失敗しました: {exc}") from exc

        url = task.output.pbr_model or task.output.model or task.output.base_model
        if not url:
            raise Mesh3DError("3Dモデルの URL が返されませんでした")

        async with httpx.AsyncClient(timeout=120) as http:
            response = await http.get(url)
            response.raise_for_status()
            data = response.content

        return MeshArtifact(data=data, format=_guess_format(url))

    async def aclose(self) -> None:
        await self._client.close()


def _guess_format(url: str) -> MeshFormat:
    path = url.split("?", 1)[0].lower()
    for candidate in ("glb", "gltf", "obj", "stl", "3mf"):
        if path.endswith(f".{candidate}"):
            return candidate  # type: ignore[return-value]
    # Tripo の既定は glTF バイナリ。拡張子が付かない URL もあるため既定値を置く。
    return "glb"


class StubMeshProvider:
    """API キーなしで開発・テストするためのスタブ.

    企画の外形寸法をそのまま箱にした STL を返す。実際の形状生成ではないが、
    「メッシュを受け取って修復・検証・保存し、アプリで表示する」までの
    経路をすべて通せる。
    """

    #: 立方体ではなく扁平な箱にしてある。生成物であることが見て分かるようにするためと、
    #: 企画の縦横比と一致しないので「寸法が食い違う」警告経路も併せて確認できるため。
    _EXTENTS = (40.0, 30.0, 20.0)

    def __init__(self) -> None:
        self._jobs: set[str] = set()
        self._counter = 0

    async def submit(self, request: GenerationRequest) -> str:
        self._counter += 1
        job_id = f"stub-job-{self._counter}"
        self._jobs.add(job_id)
        return job_id

    async def poll(self, job_id: str) -> JobState:
        if job_id not in self._jobs:
            raise Mesh3DError(f"未知のジョブです: {job_id}")
        return "done"

    async def fetch(self, job_id: str) -> MeshArtifact:
        if job_id not in self._jobs:
            raise Mesh3DError(f"未知のジョブです: {job_id}")

        import trimesh

        box = trimesh.creation.box(extents=self._EXTENTS)
        return MeshArtifact(data=box.export(file_type="stl"), format="stl")
