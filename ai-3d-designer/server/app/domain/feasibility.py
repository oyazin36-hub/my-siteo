"""企画が物理的に成立するかの検算.

寸法検証(app/services/cad.py)は**外形の箱だけ**を見ている。
そのため「高さを薄くして」に応えた結果、約束した機構が中に入らなくなっても
外形が一致していれば guaranteed で合格してしまう。実際に

    名刺30枚 / ボタン式排出 / 96 x 60 x 10.7mm

という企画が合格したが、内寸 92 x 56mm は名刺 91 x 55mm に対して片側 0.5mm
しか余裕がなく、高さも 30枚(6.9mm)を引くと 1.4mm しか残らない。
押し出し機構の入る隙間がない。

ここでは企画の数字だけで成立性を検算し、駄目なら**具体的な代案**
(必要な高さ / 入る枚数)を添えて返す。形を作る前に気付くためのもの。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import Dimensions, Proposal

#: 側壁の想定厚み (mm)。ノズル 0.4mm の 5 周ぶん。
WALL_MM = 2.0

#: 底とフタの想定厚み (mm)。
FLOOR_MM = 1.2
LID_MM = 1.2

#: 収納物のまわりに要るすきま (mm/片側)。出し入れできる最低限。
CONTENT_CLEARANCE_MM = 0.5

#: 可動機構が要る高さ方向の空間 (mm)。
#: てこ板 1.2mm + 押し下げ代 1.0mm + 逃げ 0.3mm を最低限とみて 2.5mm。
MECHANISM_HEADROOM_MM = 2.5


@dataclass(frozen=True)
class ContentSpec:
    """収納物 1 個の寸法."""

    name: str
    width_mm: float
    depth_mm: float
    thickness_mm: float


#: 収納物の実寸。枚数を数える物だけを持つ。
#: キーは capacity の文言に現れる語。
_CONTENTS: tuple[tuple[tuple[str, ...], ContentSpec], ...] = (
    (("名刺",), ContentSpec("名刺", 91.0, 55.0, 0.23)),
    (("カード", "クレジット", "IC"), ContentSpec("カード", 85.6, 53.98, 0.76)),
)

#: 「名刺30枚」「カードを20枚くらい」から個数を取る。
_COUNT_PATTERN = re.compile(r"(\d+)\s*枚")


@dataclass(frozen=True)
class ContentRequirement:
    """収納物が占める空間."""

    spec: ContentSpec
    count: int

    @property
    def stack_height_mm(self) -> float:
        return self.spec.thickness_mm * self.count

    @property
    def footprint_mm(self) -> tuple[float, float]:
        return (self.spec.width_mm, self.spec.depth_mm)

    def describe(self) -> str:
        return f"{self.spec.name}{self.count}枚({self.stack_height_mm:.1f}mm)"


def parse_capacity(capacity: str | None) -> ContentRequirement | None:
    """企画の capacity から収納物と枚数を読む.

    読めなければ None。**推測で数字を作らない**。分からないものを
    分かったことにすると、成立しない企画を成立すると言ってしまう。
    """
    if not capacity:
        return None

    count_match = _COUNT_PATTERN.search(capacity)
    if count_match is None:
        return None
    count = int(count_match.group(1))
    if count <= 0:
        return None

    for keywords, spec in _CONTENTS:
        if any(keyword in capacity for keyword in keywords):
            return ContentRequirement(spec=spec, count=count)
    return None


@dataclass(frozen=True)
class Interior:
    """外形から求めた内寸."""

    width_mm: float
    depth_mm: float
    height_mm: float

    @classmethod
    def of(cls, size: Dimensions) -> Interior:
        return cls(
            width_mm=size.width - 2 * WALL_MM,
            depth_mm=size.depth - 2 * WALL_MM,
            height_mm=size.height - FLOOR_MM - LID_MM,
        )


def _required_height(need: ContentRequirement, *, with_mechanism: bool) -> float:
    """収納物と機構に要る内寸高さ (mm)."""
    headroom = MECHANISM_HEADROOM_MM if with_mechanism else 0.0
    return need.stack_height_mm + headroom


def _max_count(interior: Interior, spec: ContentSpec, *, with_mechanism: bool) -> int:
    """この内寸に入る枚数."""
    headroom = MECHANISM_HEADROOM_MM if with_mechanism else 0.0
    usable = interior.height_mm - headroom
    if usable <= 0:
        return 0
    return max(0, int(usable / spec.thickness_mm))


def _minimum_outer_height(need: ContentRequirement, *, with_mechanism: bool) -> float:
    """この枚数を入れるのに要る外形高さ (mm)."""
    return _required_height(need, with_mechanism=with_mechanism) + FLOOR_MM + LID_MM


def check(proposal: Proposal) -> list[str]:
    """企画が成立するかを検算し、成立しない点を具体的に返す.

    返り値が空なら、少なくともこの検算では矛盾がない。
    **判断できない企画では空を返す** ので「警告が無い = 大丈夫」ではない。
    """
    need = parse_capacity(proposal.capacity)
    if need is None:
        return []

    interior = Interior.of(proposal.size_mm)
    with_mechanism = bool(proposal.mechanism)
    problems: list[str] = []

    # --- 平面: 収納物そのものが入るか ---
    content_w, content_d = need.footprint_mm
    for axis, inner, content in (
        ("幅", interior.width_mm, content_w),
        ("奥行", interior.depth_mm, content_d),
    ):
        margin = (inner - content) / 2
        if margin < CONTENT_CLEARANCE_MM:
            shortfall = (CONTENT_CLEARANCE_MM - margin) * 2
            problems.append(
                f"{axis}が足りません。{need.spec.name}({content:.1f}mm)に対し内寸"
                f" {inner:.1f}mm で、片側 {margin:.1f}mm しかありません。"
                f"外形を {shortfall:.1f}mm 広げてください"
                f"(壁 {WALL_MM}mm x 2 と すきま {CONTENT_CLEARANCE_MM}mm x 2 が要ります)。"
            )

    # --- 高さ: 収納物 + 機構が入るか ---
    required = _required_height(need, with_mechanism=with_mechanism)
    if interior.height_mm < required:
        min_outer = _minimum_outer_height(need, with_mechanism=with_mechanism)
        fits = _max_count(interior, need.spec, with_mechanism=with_mechanism)

        if with_mechanism:
            detail = (
                f"{need.describe()}と機構({MECHANISM_HEADROOM_MM}mm)で"
                f" {required:.1f}mm 要りますが、内寸高さは {interior.height_mm:.1f}mm です"
            )
            remedy = (
                f"高さを {min_outer:.1f}mm 以上にするか、"
                f"{fits}枚に減らすか、「{proposal.mechanism}」をやめてください"
            )
        else:
            detail = f"{need.describe()}に対し、内寸高さは {interior.height_mm:.1f}mm です"
            remedy = f"高さを {min_outer:.1f}mm 以上にするか、{fits}枚に減らしてください"

        problems.append(f"高さが足りません。{detail}。{remedy}。")

    return problems


def required_free_volume_mm3(proposal: Proposal) -> float | None:
    """収納物が占める体積 (mm^3)。判断できなければ None.

    出来上がったモデルの内部空間を検証する側(services/meshproc.py)で使う。
    """
    need = parse_capacity(proposal.capacity)
    if need is None:
        return None
    width, depth = need.footprint_mm
    return width * depth * need.stack_height_mm


def required_content_box_mm(proposal: Proposal) -> tuple[float, float, float] | None:
    """収納物が要る直方体 (mm)。判断できなければ None."""
    need = parse_capacity(proposal.capacity)
    if need is None:
        return None
    width, depth = need.footprint_mm
    return (width, depth, need.stack_height_mm)
