"""メッシュの正規化・修復・印刷可否検証.

AI 生成メッシュは穴が開いていることが多く、そのままではスライサが解釈できない。
DESIGN.md §5 のリスク2に対応する工程で、Phase 2 の主要な品質指標
「修復後の防水率」はここで決まる。
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from app.providers.mesh3d import MeshArtifact
from app.services import interior

#: Bambu Lab P2S の造形範囲 (mm)。
P2S_BUILD_VOLUME_MM = (256.0, 256.0, 256.0)

#: 実寸が企画値からこの割合を超えて外れたら警告する。
_SIZE_DEVIATION_TOLERANCE = 0.15


@dataclass
class MeshReport:
    """メッシュの状態。クライアントにそのまま見せる前提で作る."""

    watertight: bool
    """防水(閉じた立体)か。False のまま印刷すると破綻する。"""

    face_count: int
    size_mm: tuple[float, float, float]
    volume_mm3: float
    repair_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    content_fits: bool | None = None
    """収納物が入る空間が内部にあるか。None は未検証か判定できなかった場合。

    True でも「約束した機構が入っている」ことまでは意味しない。
    空間があることしか分からない(services/interior.py 参照)。
    """

    @property
    def printable(self) -> bool:
        return self.watertight and not self._too_large

    @property
    def _too_large(self) -> bool:
        return any(
            size > limit for size, limit in zip(self.size_mm, P2S_BUILD_VOLUME_MM, strict=True)
        )


class MeshProcessingError(Exception):
    pass


def load(artifact: MeshArtifact) -> object:
    """任意の形式を trimesh のメッシュとして読み込む.

    シーン(複数メッシュ)で返ってくる場合があるので 1 つに結合する。
    Tripo は glTF を返すため、これは例外ではなく通常経路。
    """
    import trimesh

    try:
        loaded = trimesh.load(
            io.BytesIO(artifact.data),
            file_type=artifact.format,
            force="mesh",
        )
    except Exception as exc:
        raise MeshProcessingError(
            f"メッシュを読み込めませんでした ({artifact.format}): {exc}"
        ) from exc

    if not isinstance(loaded, trimesh.Trimesh):
        raise MeshProcessingError(f"メッシュとして解釈できませんでした ({type(loaded).__name__})")
    if len(loaded.faces) == 0:
        raise MeshProcessingError("面が1つもないメッシュです")
    return loaded


def repair(mesh: object) -> list[str]:
    """その場で修復する。実施した処理の一覧を返す.

    trimesh の破壊的メソッドを使うので mesh は書き換わる。
    """
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)
    actions: list[str] = []

    before_faces = len(mesh.faces)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_infinite_values()
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) != before_faces:
        actions.append(f"不正な面を除去 ({before_faces} → {len(mesh.faces)})")

    if not mesh.is_winding_consistent:
        trimesh.repair.fix_winding(mesh)
        actions.append("面の向きを揃えた")

    if not mesh.is_watertight:
        filled = trimesh.repair.fill_holes(mesh)
        actions.append("穴を塞いだ" if filled else "穴を塞げなかった")

    # 法線が内向きだとスライサが中身を逆に解釈するので、体積の符号で判定して直す。
    if mesh.is_watertight and mesh.volume < 0:
        trimesh.repair.fix_inversion(mesh)
        actions.append("法線の内外を反転した")

    return actions


def analyze(
    mesh: object,
    repair_actions: list[str] | None = None,
    target_size_mm: tuple[float, float, float] | None = None,
    content_box_mm: tuple[float, float, float] | None = None,
) -> MeshReport:
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)

    extents = mesh.extents
    size = (float(extents[0]), float(extents[1]), float(extents[2]))
    watertight = bool(mesh.is_watertight)

    warnings: list[str] = []
    if not watertight:
        warnings.append(
            "メッシュに穴が残っています。このままでは印刷できないため、再生成をおすすめします。"
        )
    for axis, value, limit in zip("XYZ", size, P2S_BUILD_VOLUME_MM, strict=True):
        if value > limit:
            warnings.append(f"{axis}方向が造形範囲を超えています ({value:.1f}mm > {limit:.0f}mm)")
    if watertight and mesh.volume <= 0:
        warnings.append("体積が0以下です。形状が破綻している可能性があります。")

    if target_size_mm is not None:
        # 等比拡縮なので、企画の縦横比と生成物の縦横比が違うと実寸がズレる。
        # 黙って別寸法の物を渡さないよう、ズレたら必ず伝える。
        deviated = [
            f"{axis} {actual:.1f}mm (企画では {target:.1f}mm)"
            for axis, actual, target in zip("XYZ", size, target_size_mm, strict=True)
            if target > 0 and abs(actual - target) / target > _SIZE_DEVIATION_TOLERANCE
        ]
        if deviated:
            warnings.append(
                "実寸が企画値と食い違っています: "
                + " / ".join(deviated)
                + "。画像から起こしたモデルは寸法を保証できません。"
                "寸法が重要な場合は機構ルートでの作り直しが必要です。"
            )

    content_fits: bool | None = None
    if content_box_mm is not None:
        # 外形が合っていても中が詰まっていることがある。実際の形状で確かめる。
        fit = interior.content_fits(mesh, content_box_mm)
        content_fits = fit.fits
        if fit.fits is False:
            warnings.append(f"{fit.reason}。中身が入らないため作り直しが必要です。")
        elif fit.fits is None:
            warnings.append(f"収納物が入るかを確認できませんでした({fit.reason})。")

    return MeshReport(
        watertight=watertight,
        face_count=len(mesh.faces),
        size_mm=size,
        volume_mm3=float(mesh.volume) if watertight else 0.0,
        repair_actions=repair_actions or [],
        warnings=warnings,
        content_fits=content_fits,
    )


def scale_to(mesh: object, target_mm: tuple[float, float, float]) -> None:
    """最長辺が目標寸法に一致するよう等比で拡縮する.

    画像から起こしたメッシュには実寸の概念がないため、企画の寸法に合わせる。
    形を歪ませたくないので等比で行う。その結果、**各辺が目標値に一致する保証はない**
    (縦横比は元画像由来で、企画の縦横比とは無関係なため)。
    ズレた場合は analyze() が警告を出す。黙って別寸法の物を渡さないため。
    寸法を保証するのは Phase 3 の機構ルート(パラメトリック CAD)側。
    """
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)

    current = mesh.extents
    longest_current = float(max(current))
    longest_target = float(max(target_mm))
    if longest_current <= 0 or longest_target <= 0:
        return

    mesh.apply_scale(longest_target / longest_current)


def rest_on_bed(mesh: object) -> None:
    """底面が Z=0 に載るよう平行移動する。スライサでの扱いを素直にするため."""
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)
    mesh.apply_translation(-mesh.bounds[0])


def to_stl(mesh: object) -> bytes:
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)
    exported = mesh.export(file_type="stl")
    if isinstance(exported, str):  # 念のため(ASCII STL で返る実装差を吸収)
        return exported.encode("utf-8")
    return bytes(exported)


def to_glb(mesh: object) -> bytes:
    """アプリでの表示用。3Dビューアが STL を扱えないため併せて書き出す."""
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)
    return bytes(mesh.export(file_type="glb"))


@dataclass
class ProcessedMesh:
    stl: bytes
    """印刷用。スライサに渡すのはこちら。"""

    glb: bytes
    """表示用。アプリの3Dビューアが読むのはこちら。"""

    report: MeshReport


def process(
    artifact: MeshArtifact,
    *,
    target_size_mm: tuple[float, float, float] | None = None,
    content_box_mm: tuple[float, float, float] | None = None,
) -> ProcessedMesh:
    """生成物を受け取り、印刷用 STL・表示用 GLB・診断結果を返す通しの処理."""
    mesh = load(artifact)
    actions = repair(mesh)

    if target_size_mm is not None:
        scale_to(mesh, target_size_mm)
        actions.append("企画の寸法に合わせて拡縮")

    rest_on_bed(mesh)
    return ProcessedMesh(
        stl=to_stl(mesh),
        glb=to_glb(mesh),
        report=analyze(mesh, actions, target_size_mm, content_box_mm),
    )
