"""出来たモデルの中に、収納物が入る空間があるかの検証.

外形の一致(services/cad.py)と企画の検算(domain/feasibility.py)は
どちらも「外形は正しいが中が詰まっている」モデルを通してしまう。
ここはそれを実際の形状で捕まえる最後の関門。
"""

from __future__ import annotations

import asyncio
import io

import pytest
import trimesh

from app.domain.models import Dimensions, Proposal
from app.providers.openscad import OpenScadRenderer
from app.services import interior
from app.services.cad import CadService, NoRoomForContentsError
from tests.conftest import requires_openscad

# OpenSCAD で試験用の形を作るので、無い環境では丸ごと飛ばす。
pytestmark = requires_openscad

CARD_BOX = (91.0, 55.0, 6.9)


def render(source: str) -> trimesh.Trimesh:
    """OpenSCAD で形を作る.

    trimesh の boolean は manifold3d か blender を要求するので使わない。
    OpenSCAD は機構ルートで既に使っているものなので、依存は増えない。
    """
    stl = asyncio.run(OpenScadRenderer().render_stl(source))
    return trimesh.load(io.BytesIO(stl), file_type="stl", force="mesh")


def open_case(width: float, depth: float, height: float, floor: float = 1.2) -> trimesh.Trimesh:
    """上が開いたケース。空洞の深さは height - floor になる."""
    return render(
        f"difference() {{\n"
        f"  cube([{width}, {depth}, {height}]);\n"
        f"  translate([2, 2, {floor}]) cube([{width - 4}, {depth - 4}, {height}]);\n"
        f"}}"
    )


class TestContentFits:
    def test_finds_room_in_a_real_case(self) -> None:
        mesh = open_case(96, 60, 13.4)
        assert interior.content_fits(mesh, CARD_BOX).fits is True

    def test_rejects_a_solid_block(self) -> None:
        """外形は正しいが中身が詰まっている。今まで素通りしていた形."""
        mesh = render("cube([96, 60, 13.4]);")
        result = interior.content_fits(mesh, CARD_BOX)

        assert result.fits is False
        assert "入る空間が内部にありません" in result.reason

    def test_rejects_a_cavity_that_is_too_shallow(self) -> None:
        # 名刺30枚は 6.9mm。底を厚くして空洞を 4mm にすると入らない。
        mesh = open_case(96, 60, 13.4, floor=9.4)
        assert interior.content_fits(mesh, CARD_BOX).fits is False

    def test_rejects_a_cavity_that_is_too_small_in_plan(self) -> None:
        # 高さは足りるが、平面が名刺より小さい。
        mesh = open_case(70, 60, 13.4)
        assert interior.content_fits(mesh, CARD_BOX).fits is False

    def test_accepts_a_case_rotated_ninety_degrees(self) -> None:
        # 縦横が逆でも入る。ケースの向きは設計次第なので両方試す。
        mesh = open_case(60, 96, 13.4)
        assert interior.content_fits(mesh, CARD_BOX).fits is True

    def test_ignores_a_void_you_cannot_reach(self) -> None:
        """完全に密閉された空洞は数えない。物を入れられないため."""
        mesh = render(
            "difference() {\n"
            "  cube([96, 60, 13.4]);\n"
            "  translate([2, 2, 1.2]) cube([92, 56, 11.0]);\n"  # 上に 1.2mm のフタが残る
            "}"
        )

        assert mesh.is_watertight
        assert interior.content_fits(mesh, CARD_BOX).fits is False

    def test_cannot_judge_an_open_mesh(self) -> None:
        # 閉じていないと内外を決められない。分からないことを False にしない。
        mesh = render("cube([96, 60, 13.4]);")
        mesh.faces = mesh.faces[:-2]
        assert mesh.is_watertight is False

        result = interior.content_fits(mesh, CARD_BOX)
        assert result.fits is None
        assert result.undetermined


class TestPitch:
    def test_coarsens_the_grid_for_large_models(self) -> None:
        # 造形範囲いっぱいでも、格子が爆発しないこと。
        mesh = trimesh.creation.box(extents=(250, 250, 250))
        result = interior.content_fits(mesh, CARD_BOX, pitch_mm=0.05)
        assert result.pitch_mm > 0.05


@pytest.mark.asyncio
class TestCadRefusesHollowlessModels:
    async def test_fails_when_the_outer_size_matches_but_nothing_fits(self) -> None:
        """外形だけ合わせた中身の詰まったモデルを guaranteed にしない."""
        service = CadService(
            code_provider=_SolidBlockProvider(),
            renderer=OpenScadRenderer(),
            max_attempts=2,
        )

        with pytest.raises(NoRoomForContentsError) as caught:
            await service.build(_proposal())

        assert "91x55x6.9mm" in str(caught.value)

    async def test_ignores_the_check_when_contents_are_unknown(self) -> None:
        # 収納物が読み取れない企画では、この検査は行わない。
        service = CadService(
            code_provider=_SolidBlockProvider(),
            renderer=OpenScadRenderer(),
            max_attempts=1,
        )

        result = await service.build(_proposal(capacity=None))
        assert result.report.content_fits is None


def _proposal(capacity: str | None = "名刺30枚") -> Proposal:
    return Proposal(
        product_name="名刺ケース",
        concept="テスト",
        size_mm=Dimensions(width=96, depth=60, height=13.4),
        capacity=capacity,
        mechanism="ボタン式スライド排出",
        material="Bambu PETG Basic",
        print_time_est_min=180,
    )


class _SolidBlockProvider:
    """外形は合っているが中身の詰まった塊を返す."""

    async def generate(self, proposal: Proposal, **_: object) -> str:
        size = proposal.size_mm
        return f"cube([{size.width}, {size.depth}, {size.height}]);"
