"""Phase 3 の検証.

完了条件は 2 つ:
1. 機構ルートで **寸法が保証された** 3Dモデルが作れること
2. Bambu Studio で開ける 3MF が出ること
"""

from __future__ import annotations

import io
import zipfile

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.domain.models import Dimensions, Proposal
from app.providers.cadgen import StubCadProvider
from app.providers.openscad import OpenScadRenderer, UnsafeScadError, assert_safe
from app.providers.slicer import HeuristicSlicer, SlicerError
from app.services.cad import CadService, DimensionMismatchError
from app.services.threemf import ThreeMfMetadata, from_mesh, read_metadata
from tests.conftest import requires_openscad

# 機構ルートは OpenSCAD の実行ファイルが要る。
pytestmark = requires_openscad

AUTH = {"Authorization": "Bearer test-user"}
MEISHI = "名刺入れをつくって。ボタンで取り出せて、30枚入って、ポケットに入るサイズ"


def _proposal(
    width: float = 96,
    depth: float = 60,
    height: float = 13.4,
    capacity: str | None = "名刺30枚",
) -> Proposal:
    return Proposal(
        product_name="スマートスライド名刺ケース",
        concept="ボタンで名刺が持ち上がるケース",
        size_mm=Dimensions(width=width, depth=depth, height=height),
        capacity=capacity,
        mechanism="ボタン式スライド排出",
        material="Bambu PETG Basic",
        print_time_est_min=180,
        features=["窓付きフタ"],
    )


class TestOpenScadSandbox:
    """LLM が書いたコードをサーバーで実行するので、ここが信頼境界になる."""

    @pytest.mark.parametrize(
        "source",
        [
            "include <../../etc/passwd>",
            "use <secret.scad>",
            'import("/etc/shadow");',
            'surface(file="/etc/passwd");',
            'IMPORT("x");',  # 大文字でもすり抜けさせない
        ],
    )
    def test_rejects_file_access(self, source: str) -> None:
        with pytest.raises(UnsafeScadError):
            assert_safe(source)

    @pytest.mark.parametrize(
        "source",
        [
            "cube([10,10,10]);",
            "use_lid = true;\nif (use_lid) cube([5,5,5]);",  # 変数名に use を含む
            "// include <foo>\ncube([1,1,1]);",  # コメント内の禁止語
            '/* import("x") */ sphere(5);',
        ],
    )
    def test_allows_legitimate_code(self, source: str) -> None:
        assert_safe(source)  # 例外が出なければよい

    def test_rejects_oversized_source(self) -> None:
        with pytest.raises(UnsafeScadError):
            assert_safe("cube([1,1,1]);" * 20000)


@pytest.mark.asyncio
class TestDimensionGuarantee:
    """機構ルートの本体。寸法が企画値に一致することを検証してから合格にする."""

    async def test_matches_the_proposed_dimensions_exactly(self) -> None:
        service = CadService(code_provider=StubCadProvider(), renderer=OpenScadRenderer())

        result = await service.build(_proposal(96, 60, 13.4))

        assert result.attempts == 1
        assert result.report.size_mm == pytest.approx((96.0, 60.0, 13.4), abs=0.1)
        assert result.report.watertight
        assert result.report.printable
        assert result.report.warnings == []

    async def test_works_for_other_sizes(self) -> None:
        service = CadService(code_provider=StubCadProvider(), renderer=OpenScadRenderer())

        # 40 x 25.5mm に名刺(91 x 55mm)は入らない。ここで見たいのは寸法の一致だけ
        # なので、収納物を指定せず中身の検査は外す。
        result = await service.build(_proposal(40, 25.5, 8, capacity=None))

        assert result.report.size_mm == pytest.approx((40.0, 25.5, 8.0), abs=0.1)

    async def test_retries_when_the_size_is_wrong(self) -> None:
        """寸法が外れたら作り直す。何回目で合ったかを記録する."""
        provider = _WrongThenRightProvider(wrong_attempts=1)
        service = CadService(code_provider=provider, renderer=OpenScadRenderer())

        result = await service.build(_proposal(96, 60, 13.4))

        assert result.attempts == 2
        assert result.report.size_mm == pytest.approx((96.0, 60.0, 13.4), abs=0.1)
        # ずれの実測値がフィードバックされていること。
        assert provider.received_feedback is not None
        assert provider.received_feedback[0] == pytest.approx(50.0, abs=0.1)

    async def test_gives_up_and_fails_loudly(self) -> None:
        """合わないまま合格にしない。寸法保証とはそういうこと."""
        service = CadService(
            code_provider=_WrongThenRightProvider(wrong_attempts=99),
            renderer=OpenScadRenderer(),
            max_attempts=2,
        )

        with pytest.raises(DimensionMismatchError):
            await service.build(_proposal(96, 60, 13.4))

    async def test_refuses_to_render_unsafe_code(self) -> None:
        service = CadService(code_provider=_UnsafeProvider(), renderer=OpenScadRenderer())

        with pytest.raises(UnsafeScadError):
            await service.build(_proposal())


def _hollow_case(width: float, depth: float, height: float, wall: float = 2.0) -> str:
    """外形が指定どおりで、中身の入る空洞があるケース."""
    return (
        f"difference() {{\n"
        f"  cube([{width}, {depth}, {height}]);\n"
        f"  translate([{wall}, {wall}, 1.2])\n"
        f"    cube([{width - 2 * wall}, {depth - 2 * wall}, {height}]);\n"
        f"}}"
    )


class _WrongThenRightProvider:
    """最初の n 回は間違った寸法を返し、その後は正しい寸法を返す."""

    def __init__(self, wrong_attempts: int) -> None:
        self._wrong_attempts = wrong_attempts
        self._calls = 0
        self.received_feedback: tuple[float, float, float] | None = None

    async def generate(
        self,
        proposal: Proposal,
        *,
        previous_code: str | None = None,
        actual_size_mm: tuple[float, float, float] | None = None,
    ) -> str:
        if actual_size_mm is not None:
            self.received_feedback = actual_size_mm

        self._calls += 1
        if self._calls <= self._wrong_attempts:
            return "cube([50, 50, 50]);"

        # 中空のケース。中身の入る空間まで見るようになったので、
        # 詰まった立方体では正解にならない。
        size = proposal.size_mm
        return _hollow_case(size.width, size.depth, size.height)


class _UnsafeProvider:
    async def generate(self, proposal: Proposal, **_: object) -> str:
        return "include <../../etc/passwd>\ncube([10,10,10]);"


class TestThreeMf:
    def test_writes_a_valid_archive_in_millimetres(self) -> None:
        stl = trimesh.creation.box(extents=(96, 60, 13.4)).export(file_type="stl")

        archive = from_mesh(stl, ThreeMfMetadata(title="名刺ケース", description="テスト"))

        zipped = zipfile.ZipFile(io.BytesIO(archive))
        assert zipped.testzip() is None
        assert "3D/3dmodel.model" in zipped.namelist()

        xml = zipped.read("3D/3dmodel.model").decode("utf-8")
        # スライサが実寸を正しく解釈するには単位の指定が要る。
        assert 'unit="millimeter"' in xml

    def test_round_trips_with_the_original_dimensions(self) -> None:
        stl = trimesh.creation.box(extents=(96, 60, 13.4)).export(file_type="stl")

        archive = from_mesh(stl, ThreeMfMetadata(title="x"))
        reloaded = trimesh.load(io.BytesIO(archive), file_type="3mf", force="mesh")

        assert tuple(round(float(v), 1) for v in reloaded.extents) == (96.0, 60.0, 13.4)

    def test_carries_the_product_name(self) -> None:
        stl = trimesh.creation.box(extents=(10, 10, 10)).export(file_type="stl")

        archive = from_mesh(
            stl, ThreeMfMetadata(title="スマートスライド名刺ケース", description="名刺30枚")
        )

        metadata = read_metadata(archive)
        assert metadata["Title"] == "スマートスライド名刺ケース"
        assert metadata["Description"] == "名刺30枚"

    def test_escapes_special_characters(self) -> None:
        stl = trimesh.creation.box(extents=(10, 10, 10)).export(file_type="stl")

        archive = from_mesh(stl, ThreeMfMetadata(title='A & B <C> "D"'))

        # XML が壊れず読み戻せること。
        assert read_metadata(archive)["Title"] == "A &amp; B &lt;C&gt; &quot;D&quot;"


@pytest.mark.asyncio
class TestEstimates:
    async def test_estimates_from_volume(self) -> None:
        stl = trimesh.creation.box(extents=(96, 60, 13.4)).export(file_type="stl")

        estimate = await HeuristicSlicer().estimate(
            model_bytes=stl, material="Bambu PETG Basic", filename="model.stl"
        )

        assert estimate.print_time_min > 0
        assert estimate.filament_grams > 0
        # 概算であることを隠さない。
        assert estimate.estimated is True

    async def test_refuses_to_guess_for_a_broken_mesh(self) -> None:
        import numpy as np

        broken = trimesh.creation.box(extents=(20, 20, 20))
        broken.update_faces(np.arange(len(broken.faces)) > 1)

        with pytest.raises(SlicerError):
            await HeuristicSlicer().estimate(
                model_bytes=broken.export(file_type="stl"),
                material="PLA",
                filename="model.stl",
            )


class TestPrintDataEndpoint:
    def _through_model(self, client: TestClient, text: str = MEISHI) -> dict:
        project = client.post("/projects", json={"text": text}, headers=AUTH).json()
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        client.post(f"/projects/{project['id']}/images", headers=AUTH)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)
        return client.get(f"/projects/{project['id']}", headers=AUTH).json()

    def test_mechanism_route_is_dimension_guaranteed(self, client: TestClient) -> None:
        project = self._through_model(client)

        assert project["route"] == "mechanism"
        model = project["model"]
        assert model["gen_source"] == "parametric"
        assert model["dimensional_accuracy"] == "guaranteed"
        assert model["source_code"]  # 後から寸法を追えるよう残す
        assert model["attempts"] >= 1

        # 企画値と実寸が一致していること。
        size = model["size_mm"]
        proposed = project["proposal"]["size_mm"]
        for axis in ("width", "depth", "height"):
            assert size[axis] == pytest.approx(proposed[axis], abs=0.1)

        # 寸法が合っているので食い違い警告は出ない。
        assert not any("食い違" in w for w in model["warnings"])

    def test_produces_a_downloadable_3mf(self, client: TestClient) -> None:
        project = self._through_model(client)

        response = client.post(f"/projects/{project['id']}/print", headers=AUTH)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "print_ready"
        print_data = body["print_data"]
        assert print_data["url"].endswith(".3mf")
        assert print_data["print_time_min"] > 0
        assert print_data["filament_grams"] > 0
        assert print_data["material"] == project["proposal"]["material"]

        served = client.get(print_data["url"])
        assert served.status_code == 200
        assert zipfile.ZipFile(io.BytesIO(served.content)).testzip() is None

    def test_tells_the_user_what_still_needs_doing_by_hand(self, client: TestClient) -> None:
        project = self._through_model(client)
        body = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()

        warnings = body["print_data"]["warnings"]
        # 造形の向きとサポート材は人が確認する前提。ここを黙ると印刷が失敗する。
        assert any("サポート材" in w for w in warnings)
        assert any("プリセット" in w for w in warnings)
        # 概算であることを伝える。
        assert body["print_data"]["estimated"] is True
        assert any("概算" in w for w in warnings)

    def test_rebuilds_to_reflect_ams_registered_afterwards(self, client: TestClient) -> None:
        """AMS を後から登録しても印刷データを作り直せること.

        作り直せないと「今なにが入っているか」を登録する意味がなくなる。
        """
        project = self._through_model(client)
        first = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()

        # 未登録なので、全パーツが「要装填」。
        before = first["print_data"]["ams_plan"]["assignments"]
        assert all(a["needs_loading"] for a in before)

        client.put(
            "/me/ams",
            json={
                "connected": True,
                "slots": [
                    {"slot": 1, "product": "Bambu PLA Basic", "color": "White"},
                    {"slot": 2, "product": "Bambu PETG Basic", "color": "Black"},
                    {"slot": 3, "product": "Bambu PLA Basic", "color": "Orange"},
                ],
            },
            headers=AUTH,
        )

        second = client.post(f"/projects/{project['id']}/print", headers=AUTH)
        assert second.status_code == 200, second.text
        after = second.json()["print_data"]["ams_plan"]["assignments"]

        # 同じパーツ構成のまま、装填済みのスロットを指すようになる。
        assert [a["part"] for a in after] == [a["part"] for a in before]
        assert not any(a["needs_loading"] for a in after)

    def test_rebuild_produces_a_fresh_3mf(self, client: TestClient) -> None:
        project = self._through_model(client)
        first = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()
        second = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()

        # 古い URL を上書きしない。ダウンロード済みのリンクを壊さないため。
        assert second["print_data"]["url"] != first["print_data"]["url"]
        assert client.get(first["print_data"]["url"]).status_code == 200
        assert client.get(second["print_data"]["url"]).status_code == 200

    def test_cannot_build_before_a_model_exists(self, client: TestClient) -> None:
        project = client.post("/projects", json={"text": MEISHI}, headers=AUTH).json()
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)

        response = client.post(f"/projects/{project['id']}/print", headers=AUTH)
        assert response.status_code == 409

    def test_other_users_cannot_build(self, client: TestClient) -> None:
        project = self._through_model(client)
        response = client.post(
            f"/projects/{project['id']}/print",
            headers={"Authorization": "Bearer someone-else"},
        )
        assert response.status_code == 404
