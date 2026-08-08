"""企画の成立性検算.

実際に通しで動かしたときに見つかった問題を固定する。
「もう少し薄くして」に応えた結果、約束したボタン機構が入らなくなったのに
外形が一致していたので guaranteed で合格していた。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain import feasibility
from app.domain.models import Dimensions, Proposal

AUTH = {"Authorization": "Bearer demo-user"}
MEISHI = "名刺入れをつくって。ボタンを押したら名刺が取り出せる。名刺は30枚くらい。"


def proposal(
    *,
    height: float,
    width: float = 96.0,
    depth: float = 60.0,
    capacity: str | None = "名刺30枚",
    mechanism: str | None = "ボタン式スライド排出",
) -> Proposal:
    return Proposal(
        product_name="スマートスライド名刺ケース",
        concept="ボタンで名刺が持ち上がるケース",
        size_mm=Dimensions(width=width, depth=depth, height=height),
        capacity=capacity,
        mechanism=mechanism,
        material="Bambu PETG Basic",
        print_time_est_min=180,
    )


class TestCapacityParsing:
    def test_reads_the_item_and_the_count(self) -> None:
        need = feasibility.parse_capacity("名刺30枚")
        assert need is not None
        assert need.spec.name == "名刺"
        assert need.count == 30
        assert need.stack_height_mm == pytest.approx(6.9, abs=0.01)

    def test_reads_a_looser_phrasing(self) -> None:
        need = feasibility.parse_capacity("名刺を30枚くらい")
        assert need is not None and need.count == 30

    @pytest.mark.parametrize(
        "capacity",
        [None, "", "たっぷり入る", "小物入れ", "名刺"],
    )
    def test_does_not_guess_when_it_cannot_tell(self, capacity: str | None) -> None:
        # 分からないものを分かったことにすると、成立しない企画を通してしまう。
        assert feasibility.parse_capacity(capacity) is None


class TestHeight:
    def test_rejects_the_thickness_that_squeezes_out_the_mechanism(self) -> None:
        """実際に起きたケース。96 x 60 x 10.7mm では機構が入らない."""
        problems = feasibility.check(proposal(height=10.7))

        assert len(problems) == 1
        message = problems[0]
        assert "高さが足りません" in message
        # 具体的な代案が要る。「入りません」だけでは次の一手が決まらない。
        assert "11.8mm 以上" in message
        assert "25枚" in message
        assert "ボタン式スライド排出" in message

    def test_accepts_the_original_thickness(self) -> None:
        # 修正前の企画値。ここでは成立していた。
        assert feasibility.check(proposal(height=13.4)) == []

    def test_the_same_thickness_is_fine_without_a_mechanism(self) -> None:
        # 機構が無ければ 10.7mm でも名刺30枚は入る。厚みだけの問題ではない。
        assert feasibility.check(proposal(height=10.7, mechanism=None)) == []

    def test_boundary_is_not_off_by_one(self) -> None:
        # 名刺30枚 6.9 + 機構 2.5 = 9.4mm、これに底1.2とフタ1.2で 11.8mm。
        assert feasibility.check(proposal(height=11.8)) == []
        assert feasibility.check(proposal(height=11.7)) != []


class TestFootprint:
    def test_rejects_a_case_narrower_than_the_card(self) -> None:
        problems = feasibility.check(proposal(height=13.4, width=80.0))

        assert any("幅が足りません" in p for p in problems)
        assert any("16.0mm 広げて" in p for p in problems)

    def test_rejects_the_margin_that_leaves_no_clearance(self) -> None:
        # 内寸 91.0mm ちょうど。名刺は入るが出し入れできない。
        problems = feasibility.check(proposal(height=13.4, width=95.0))
        assert any("幅が足りません" in p for p in problems)

    def test_reports_both_axes(self) -> None:
        problems = feasibility.check(proposal(height=13.4, width=80.0, depth=40.0))
        assert any("幅が足りません" in p for p in problems)
        assert any("奥行が足りません" in p for p in problems)


class TestUnknownContents:
    def test_stays_silent_when_it_cannot_judge(self) -> None:
        # 検算できないものを警告しない。狼少年になると誰も読まなくなる。
        assert feasibility.check(proposal(height=1.0, capacity="小物いろいろ")) == []


class TestRequiredSpace:
    def test_reports_the_box_the_contents_need(self) -> None:
        box = feasibility.required_content_box_mm(proposal(height=13.4))
        assert box is not None
        assert box == pytest.approx((91.0, 55.0, 6.9), abs=0.01)

    def test_reports_nothing_when_contents_are_unknown(self) -> None:
        assert feasibility.required_content_box_mm(proposal(height=13.4, capacity=None)) is None


class TestSurfacedThroughTheApi:
    def test_the_proposal_carries_the_problem(self, client: TestClient) -> None:
        project = client.post("/projects", json={"text": MEISHI}, headers=AUTH).json()
        body = client.post(f"/projects/{project['id']}/proposal", headers=AUTH).json()

        # スタブの企画は 13.4mm なので、この時点では成立している。
        assert body["proposal"]["warnings"] == []

        revised = client.post(
            f"/projects/{project['id']}/proposal/revise",
            json={"request": "もう少し薄くして"},
            headers=AUTH,
        ).json()

        # 薄くした結果、機構が入らなくなったことを企画の時点で伝える。
        warnings = revised["proposal"]["warnings"]
        assert any("高さが足りません" in w for w in warnings), warnings

    def test_warnings_survive_a_reload(self, client: TestClient) -> None:
        project = client.post("/projects", json={"text": MEISHI}, headers=AUTH).json()
        client.post(f"/projects/{project['id']}/proposal", headers=AUTH)
        client.post(
            f"/projects/{project['id']}/proposal/revise",
            json={"request": "もう少し薄くして"},
            headers=AUTH,
        )

        reloaded = client.get(f"/projects/{project['id']}", headers=AUTH).json()
        assert reloaded["proposal"]["warnings"]
