"""メッシュ処理の検証.

DESIGN.md §5 のリスク2「AI生成メッシュは穴が開きがち」への対策が
実際に機能していることを保証する。
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.providers.mesh3d import MeshArtifact
from app.services import meshproc


def _stl(mesh: trimesh.Trimesh) -> MeshArtifact:
    return MeshArtifact(data=mesh.export(file_type="stl"), format="stl")


def _box_with_hole(extents: tuple[float, float, float] = (20, 20, 20)) -> trimesh.Trimesh:
    """面を2枚削って穴を開けた箱。AI生成メッシュの典型的な壊れ方を再現する."""
    box = trimesh.creation.box(extents=extents)
    box.update_faces(np.arange(len(box.faces)) > 1)
    return box


class TestRepair:
    def test_fills_holes_and_restores_watertightness(self) -> None:
        broken = _box_with_hole()
        assert not broken.is_watertight  # 前提の確認

        report = meshproc.process(_stl(broken)).report

        assert report.watertight
        assert report.printable
        assert "穴を塞いだ" in report.repair_actions

    def test_leaves_a_sound_mesh_alone(self) -> None:
        sound = trimesh.creation.box(extents=(20, 20, 20))

        report = meshproc.process(_stl(sound)).report

        assert report.watertight
        assert report.repair_actions == []


class TestPrintability:
    def test_rejects_a_model_larger_than_the_build_volume(self) -> None:
        huge = trimesh.creation.box(extents=(300, 10, 10))

        report = meshproc.process(_stl(huge)).report

        assert not report.printable
        assert any("造形範囲を超えています" in w for w in report.warnings)

    def test_reports_size_deviation_from_the_proposal(self) -> None:
        # 立方体を 96x60x13.4 に合わせても、等比拡縮では各辺は一致しない。
        # 黙って別寸法の物を渡さないことを保証する。
        cube = trimesh.creation.box(extents=(20, 20, 20))

        report = meshproc.process(_stl(cube), target_size_mm=(96, 60, 13.4)).report

        assert any("実寸が企画値と食い違っています" in w for w in report.warnings)
        assert any("寸法を保証できません" in w for w in report.warnings)

    def test_stays_quiet_when_the_size_matches(self) -> None:
        matching = trimesh.creation.box(extents=(96, 60, 13.4))

        report = meshproc.process(_stl(matching), target_size_mm=(96, 60, 13.4)).report

        assert report.warnings == []
        assert report.printable


class TestFormats:
    def test_reads_glb(self) -> None:
        # Tripo3D は glTF バイナリを返すので、これが実際の経路になる。
        box = trimesh.creation.box(extents=(30, 20, 10))
        artifact = MeshArtifact(data=box.export(file_type="glb"), format="glb")

        processed = meshproc.process(artifact)
        stl, report = processed.stl, processed.report

        assert report.watertight
        assert stl.startswith(b"solid") or len(stl) > 84  # ASCII か binary STL
        assert tuple(round(v) for v in report.size_mm) == (30, 20, 10)

    def test_rejects_unreadable_data(self) -> None:
        with pytest.raises(meshproc.MeshProcessingError):
            meshproc.process(MeshArtifact(data=b"not a mesh", format="stl"))


class TestPlacement:
    def test_rests_the_model_on_the_bed(self) -> None:
        floating = trimesh.creation.box(extents=(10, 10, 10))
        floating.apply_translation([5, 5, 50])

        stl = meshproc.process(_stl(floating)).stl
        result = trimesh.load(trimesh.util.wrap_as_stream(stl), file_type="stl", force="mesh")

        # Z の最小が 0 に載っていること。スライサでの扱いを素直にするため。
        assert result.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
