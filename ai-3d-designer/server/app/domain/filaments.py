"""Bambu Lab 純正フィラメントのマスターデータ.

公開 API が存在しないため、アプリ内のデータとして持つ(DESIGN.md §2 の補足)。
ラインナップは変わるので、**このファイルだけを更新すれば追従できる**構造にしてある。

数値は公称値。印刷条件で変わるため、選定の判断材料として使う。
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class Strength(IntEnum):
    """強度の段階。比較したいので順序を持つ."""

    low = 1
    medium = 2
    high = 3


class Material(StrEnum):
    pla = "PLA"
    petg = "PETG"
    abs = "ABS"
    asa = "ASA"
    tpu = "TPU"
    pa = "PA"


class Filament(BaseModel):
    """カタログの1行."""

    id: str
    product: str
    material: Material
    colors: list[str]

    strength: Strength
    heat_resist_c: int
    """荷重たわみ温度の目安。夏の車内は 60〜80℃ になりうる。"""

    flexible: bool
    ams_compatible: bool
    enclosure_recommended: bool = False
    """反りやすく、囲いのある機種でないと失敗しやすい素材。"""

    notes: str = ""

    def has_color(self, color: str) -> bool:
        return color in self.colors


#: 代表的な色。カタログ全体で表記を揃えるために定数化する。
BLACK = "Black"
WHITE = "White"
GRAY = "Gray"
ORANGE = "Orange"
RED = "Red"
BLUE = "Blue"
GREEN = "Green"
YELLOW = "Yellow"
BEIGE = "Beige"

_COMMON_COLORS = [BLACK, WHITE, GRAY, ORANGE, RED, BLUE, GREEN, YELLOW]

CATALOG: list[Filament] = [
    Filament(
        id="pla_basic",
        product="Bambu PLA Basic",
        material=Material.pla,
        colors=[*_COMMON_COLORS, BEIGE],
        strength=Strength.low,
        heat_resist_c=55,
        flexible=False,
        ams_compatible=True,
        notes="最も扱いやすい。装飾や試作の既定。熱と衝撃に弱い。",
    ),
    Filament(
        id="pla_matte",
        product="Bambu PLA Matte",
        material=Material.pla,
        colors=[BLACK, WHITE, GRAY, BEIGE, BLUE],
        strength=Strength.low,
        heat_resist_c=55,
        flexible=False,
        ams_compatible=True,
        notes="積層跡が目立ちにくい。見た目重視の外装向け。",
    ),
    Filament(
        id="petg_basic",
        product="Bambu PETG Basic",
        material=Material.petg,
        colors=_COMMON_COLORS,
        strength=Strength.medium,
        heat_resist_c=70,
        flexible=False,
        ams_compatible=True,
        notes="粘りがあり割れにくい。ヒンジや板バネなど繰り返し曲がる部品に向く。",
    ),
    Filament(
        id="petg_hf",
        product="Bambu PETG HF",
        material=Material.petg,
        colors=[BLACK, WHITE, GRAY, ORANGE],
        strength=Strength.medium,
        heat_resist_c=70,
        flexible=False,
        ams_compatible=True,
        notes="PETG Basic より高速に印刷できる。",
    ),
    Filament(
        id="abs",
        product="Bambu ABS",
        material=Material.abs,
        colors=[BLACK, WHITE, GRAY, RED, BLUE],
        strength=Strength.high,
        heat_resist_c=95,
        flexible=False,
        ams_compatible=True,
        enclosure_recommended=True,
        notes="耐熱と強度が高いが反りやすい。囲いのある機種向け。",
    ),
    Filament(
        id="asa",
        product="Bambu ASA",
        material=Material.asa,
        colors=[BLACK, WHITE, GRAY],
        strength=Strength.high,
        heat_resist_c=95,
        flexible=False,
        ams_compatible=True,
        enclosure_recommended=True,
        notes="ABS 同等の強度に加えて紫外線に強い。屋外向け。",
    ),
    Filament(
        id="tpu_95a",
        product="Bambu TPU 95A HF",
        material=Material.tpu,
        colors=[BLACK, WHITE, RED, BLUE],
        strength=Strength.medium,
        heat_resist_c=60,
        flexible=True,
        ams_compatible=False,
        notes="ゴム状に曲がる。AMS を通せないため外部スプールから給送する。",
    ),
    Filament(
        id="paht_cf",
        product="Bambu PAHT-CF",
        material=Material.pa,
        colors=[BLACK],
        strength=Strength.high,
        heat_resist_c=120,
        flexible=False,
        ams_compatible=True,
        enclosure_recommended=True,
        notes="炭素繊維入りナイロン。機械部品向けだが吸湿しやすく扱いが難しい。",
    ),
]

_BY_ID = {item.id: item for item in CATALOG}
_BY_PRODUCT = {item.product: item for item in CATALOG}


def by_id(filament_id: str) -> Filament | None:
    return _BY_ID.get(filament_id)


def by_product(product: str) -> Filament | None:
    return _BY_PRODUCT.get(product)


class PartRequirement(BaseModel):
    """1 パーツに求められる性質。LLM がここまでを判断する."""

    name: str = Field(min_length=1)
    """パーツ名。例: 本体 / ボタン / ロゴ"""

    role: str = ""
    """何のための部品か。選定理由の説明に使う。"""

    min_strength: Strength = Strength.low
    needs_flexibility: bool = False
    min_heat_resist_c: int = 0
    preferred_color: str | None = None
    volume_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    """全体の材料量に占めるおおよその割合。使用量の按分に使う。"""


class NoSuitableFilamentError(Exception):
    def __init__(self, requirement: PartRequirement) -> None:
        super().__init__(
            f"「{requirement.name}」の要件を満たす純正フィラメントが見つかりません "
            f"(強度>={requirement.min_strength.name} / 耐熱>={requirement.min_heat_resist_c}℃ / "
            f"柔軟性={'必要' if requirement.needs_flexibility else '不要'})"
        )
        self.requirement = requirement


def select(
    requirement: PartRequirement,
    *,
    catalog: list[Filament] | None = None,
    prefer_ams: bool = True,
) -> tuple[Filament, str, str]:
    """要件からフィラメントと色を選ぶ。返り値は (フィラメント, 色, 理由).

    判断そのものはここで決定的に行う。LLM に任せると同じ入力で結果が揺れ、
    「なぜこれが選ばれたか」も説明できなくなるため。
    """
    items = catalog if catalog is not None else CATALOG

    candidates = [
        item
        for item in items
        if item.flexible == requirement.needs_flexibility
        and item.strength >= requirement.min_strength
        and item.heat_resist_c >= requirement.min_heat_resist_c
    ]
    if not candidates:
        raise NoSuitableFilamentError(requirement)

    def rank(item: Filament) -> tuple[int, int, int, int]:
        # 1. AMS を通せるものを優先(自動色替えができる)
        # 2. 希望色があるものを優先
        # 3. 囲いが要らないものを優先(P2S は開放型)
        # 4. 過剰な性能を避ける(扱いやすさとコストのため)
        return (
            0 if (item.ams_compatible or not prefer_ams) else 1,
            0
            if requirement.preferred_color is None or item.has_color(requirement.preferred_color)
            else 1,
            1 if item.enclosure_recommended else 0,
            item.strength,
        )

    best = min(candidates, key=rank)
    color = _pick_color(best, requirement.preferred_color)
    return best, color, _explain(best, requirement, color)


def _pick_color(filament: Filament, preferred: str | None) -> str:
    if preferred is not None and filament.has_color(preferred):
        return preferred
    return filament.colors[0]


def _explain(filament: Filament, requirement: PartRequirement, color: str) -> str:
    """なぜこれが選ばれたかを 1 文で説明する。選定が決定的だからこそ理由を書ける."""
    reasons: list[str] = []
    if requirement.needs_flexibility:
        reasons.append("柔軟性が必要")
    if requirement.min_strength >= Strength.high:
        reasons.append("高い強度が必要")
    elif requirement.min_strength == Strength.medium:
        reasons.append("繰り返しの力がかかる")
    if requirement.min_heat_resist_c > 60:
        reasons.append(f"{requirement.min_heat_resist_c}℃ 以上の耐熱が必要")

    head = "、".join(reasons) + "ため" if reasons else "扱いやすさを優先して"
    sentences = [f"{head}{filament.product}({color})を選びました。"]

    if requirement.preferred_color and color != requirement.preferred_color:
        sentences.append(
            f"希望の {requirement.preferred_color} はこの素材に取り扱いがないため "
            f"{color} にしています。"
        )
    if filament.notes:
        sentences.append(filament.notes)
    if filament.enclosure_recommended:
        sentences.append("反りやすい素材なので、造形が浮く場合は囲いを検討してください。")
    if not filament.ams_compatible:
        sentences.append("AMS を通せないため、外部スプールから給送してください。")

    return "".join(sentences)
