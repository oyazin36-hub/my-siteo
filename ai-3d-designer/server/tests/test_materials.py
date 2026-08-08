"""Phase 4 の検証: フィラメント選定と AMS スロット配置.

完了条件: 「本体 PETG黒 + 装飾 PLAオレンジ、Slot1〜3 配置案」まで自動提示される。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.ams import AmsState, LoadedSlot
from app.domain.filaments import (
    CATALOG,
    NoSuitableFilamentError,
    PartRequirement,
    Strength,
    by_product,
    select,
)
from app.domain.models import Dimensions, Proposal
from app.providers.parts import StubPartsDecomposer
from app.services.materials import MaterialsService

AUTH = {"Authorization": "Bearer test-user"}
MEISHI = "名刺入れをつくって。ボタンで取り出せて、30枚入って、ポケットに入るサイズ"


def _proposal() -> Proposal:
    return Proposal(
        product_name="スマートスライド名刺ケース",
        concept="ボタンを押すとフタが開き名刺が持ち上がるケース",
        size_mm=Dimensions(width=96, depth=60, height=13.4),
        capacity="名刺30枚",
        mechanism="ボタン式スライド排出",
        material="Bambu PETG Basic",
        print_time_est_min=180,
        features=["窓付きフタ", "板バネを一体成形"],
    )


class TestFilamentSelection:
    """選定は決定的なルールで行う。同じ入力で必ず同じ結果になること."""

    def test_is_deterministic(self) -> None:
        requirement = PartRequirement(name="本体", min_strength=Strength.medium)

        results = {select(requirement)[0].id for _ in range(10)}

        assert len(results) == 1

    def test_picks_petg_for_parts_that_flex_repeatedly(self) -> None:
        filament, color, reason = select(
            PartRequirement(name="板バネ", min_strength=Strength.medium, preferred_color="Black")
        )

        assert filament.product == "Bambu PETG Basic"
        assert color == "Black"
        assert "繰り返しの力がかかる" in reason

    def test_picks_pla_for_decoration(self) -> None:
        filament, color, _ = select(PartRequirement(name="ロゴ", preferred_color="Orange"))

        # 力がかからない部品に過剰な素材を当てない。
        assert filament.product == "Bambu PLA Basic"
        assert color == "Orange"

    def test_picks_tpu_when_flexibility_is_required(self) -> None:
        filament, _, reason = select(PartRequirement(name="滑り止め", needs_flexibility=True))

        assert filament.material == "TPU"
        assert not filament.ams_compatible
        # AMS を通せないことを必ず伝える。
        assert "外部スプール" in reason

    def test_meets_heat_resistance(self) -> None:
        filament, _, _ = select(PartRequirement(name="本体", min_heat_resist_c=90))

        assert filament.heat_resist_c >= 90

    def test_says_so_when_the_colour_is_unavailable(self) -> None:
        _, color, reason = select(
            PartRequirement(name="本体", min_heat_resist_c=90, preferred_color="Yellow")
        )

        # 黙って別の色にしない。
        assert color != "Yellow"
        assert "Yellow" in reason
        assert "取り扱いがない" in reason

    def test_prefers_ams_compatible_filaments(self) -> None:
        filament, _, _ = select(PartRequirement(name="本体"))
        assert filament.ams_compatible

    def test_refuses_impossible_requirements(self) -> None:
        # 満たせないものを近いもので埋めない。
        with pytest.raises(NoSuitableFilamentError):
            select(
                PartRequirement(name="無理な部品", needs_flexibility=True, min_heat_resist_c=150)
            )


class TestCatalog:
    def test_every_entry_has_at_least_one_colour(self) -> None:
        assert all(item.colors for item in CATALOG)

    def test_lookup_by_product_name(self) -> None:
        assert by_product("Bambu PETG Basic") is not None
        assert by_product("存在しない製品") is None


@pytest.mark.asyncio
class TestAmsPlanning:
    async def test_proposes_what_to_load_when_ams_is_unregistered(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())

        plan = await service.plan(_proposal(), total_grams=45.0)

        assert plan.assignments
        assert all(a.needs_loading for a in plan.assignments)
        assert any("未登録" in w for w in plan.warnings)

    async def test_shares_one_slot_between_parts_using_the_same_filament(self) -> None:
        """スロットは4つしかないので、同じフィラメントを別スロットに割り当てない."""
        service = MaterialsService(decomposer=StubPartsDecomposer())

        plan = await service.plan(_proposal(), total_grams=45.0)

        by_filament: dict[tuple[str, str], set[int | None]] = {}
        for a in plan.assignments:
            by_filament.setdefault((a.product, a.color), set()).add(a.slot)
        assert all(len(slots) == 1 for slots in by_filament.values())

    async def test_maps_parts_to_the_slots_already_loaded(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())
        ams = AmsState(
            connected=True,
            slots=[
                LoadedSlot(slot=1, product="Bambu PLA Basic", color="White"),
                LoadedSlot(slot=2, product="Bambu PETG Basic", color="Black"),
                LoadedSlot(slot=3, product="Bambu PLA Basic", color="Orange"),
            ],
        )

        plan = await service.plan(_proposal(), total_grams=45.0, ams=ams)

        body = next(a for a in plan.assignments if a.part == "本体")
        assert body.slot == 2  # PETG Black が入っているスロット
        assert not body.needs_loading

        button = next(a for a in plan.assignments if a.part == "ボタン")
        assert button.slot == 3  # PLA Orange
        assert not button.needs_loading

    async def test_flags_filaments_that_are_not_loaded(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())
        ams = AmsState(
            connected=True,
            slots=[LoadedSlot(slot=1, product="Bambu PETG Basic", color="Black")],
        )

        plan = await service.plan(_proposal(), total_grams=45.0, ams=ams)

        assert plan.requires_loading
        assert any("未装填" in w for w in plan.warnings)

    async def test_warns_when_the_slots_run_out(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())
        requirements = [
            PartRequirement(name=f"パーツ{i}", preferred_color=color, volume_ratio=0.2)
            for i, color in enumerate(["Black", "White", "Orange", "Red", "Blue"])
        ]

        plan = service.plan_for_requirements(requirements, total_grams=50.0)

        assert any("空きスロットがありません" in w for w in plan.warnings)

    async def test_splits_the_weight_across_parts(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())

        plan = await service.plan(_proposal(), total_grams=45.0)

        total = sum(a.grams for a in plan.assignments)
        assert total == pytest.approx(45.0, abs=0.5)

    async def test_warns_about_the_cost_of_multi_colour(self) -> None:
        service = MaterialsService(decomposer=StubPartsDecomposer())

        plan = await service.plan(_proposal(), total_grams=45.0)

        assert any("色替え" in w for w in plan.warnings)


class TestAmsEndpoints:
    def test_registers_the_loaded_slots(self, client: TestClient) -> None:
        response = client.put(
            "/me/ams",
            json={
                "connected": True,
                "slots": [
                    {"slot": 1, "product": "Bambu PETG Basic", "color": "Black"},
                    {"slot": 2, "product": "Bambu PLA Basic", "color": "Orange"},
                ],
            },
            headers=AUTH,
        )

        assert response.status_code == 200, response.text
        assert response.json()["ams"]["connected"] is True

        stored = client.get("/me/settings", headers=AUTH).json()
        assert len(stored["ams"]["slots"]) == 2

    def test_rejects_a_filament_that_is_not_in_the_catalogue(self, client: TestClient) -> None:
        response = client.put(
            "/me/ams",
            json={"slots": [{"slot": 1, "product": "架空のフィラメント", "color": "Black"}]},
            headers=AUTH,
        )
        assert response.status_code == 400

    def test_rejects_a_colour_that_is_not_stocked(self, client: TestClient) -> None:
        response = client.put(
            "/me/ams",
            json={"slots": [{"slot": 1, "product": "Bambu PAHT-CF", "color": "Orange"}]},
            headers=AUTH,
        )
        assert response.status_code == 400

    def test_rejects_filaments_that_cannot_pass_through_the_ams(self, client: TestClient) -> None:
        response = client.put(
            "/me/ams",
            json={"slots": [{"slot": 1, "product": "Bambu TPU 95A HF", "color": "Black"}]},
            headers=AUTH,
        )
        assert response.status_code == 400

    def test_rejects_duplicate_slots(self, client: TestClient) -> None:
        response = client.put(
            "/me/ams",
            json={
                "slots": [
                    {"slot": 1, "product": "Bambu PLA Basic", "color": "Black"},
                    {"slot": 1, "product": "Bambu PLA Basic", "color": "White"},
                ]
            },
            headers=AUTH,
        )
        assert response.status_code == 400

    def test_settings_require_authentication(self, client: TestClient) -> None:
        assert client.get("/me/settings").status_code == 401

    def test_serves_the_catalogue(self, client: TestClient) -> None:
        response = client.get("/me/filaments", headers=AUTH)

        assert response.status_code == 200
        products = {item["product"] for item in response.json()}
        assert "Bambu PLA Basic" in products
        assert "Bambu PETG Basic" in products


class TestEndToEnd:
    """Phase 4 の完了条件そのもの."""

    def _through_model(self, client: TestClient) -> dict:
        project = client.post("/projects", json={"text": MEISHI}, headers=AUTH).json()
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        client.post(f"/projects/{project['id']}/images", headers=AUTH)
        client.post(f"/projects/{project['id']}/model", headers=AUTH)
        return client.get(f"/projects/{project['id']}", headers=AUTH).json()

    def test_produces_a_slot_plan_with_the_print_data(self, client: TestClient) -> None:
        project = self._through_model(client)

        body = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()
        plan = body["print_data"]["ams_plan"]

        assert plan is not None
        assert plan["assignments"]
        for assignment in plan["assignments"]:
            assert assignment["part"]
            assert assignment["product"].startswith("Bambu")
            assert assignment["color"]
            assert assignment["reason"]  # なぜ選ばれたかを必ず説明する

    def test_uses_the_registered_ams_state(self, client: TestClient) -> None:
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
        project = self._through_model(client)

        body = client.post(f"/projects/{project['id']}/print", headers=AUTH).json()
        plan = body["print_data"]["ams_plan"]

        # 登録済みなので「未登録」の断りは出ない。
        assert not any("未登録" in w for w in plan["warnings"])
        body_part = next(a for a in plan["assignments"] if a["part"] == "本体")
        assert body_part["slot"] == 2
        assert body_part["needs_loading"] is False
