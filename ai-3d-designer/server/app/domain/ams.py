"""AMS(自動材料システム)のスロット管理.

AMS は 4 スロットにフィラメントを装填しておくと自動で色を切り替える装置。
「今なにが入っているか」はユーザーにしか分からないので登録してもらい、
それに合わせてパーツを割り当てる。未登録なら「何を入れるべきか」を提案する。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: AMS 1 台のスロット数。
AMS_SLOT_COUNT = 4


class LoadedSlot(BaseModel):
    """ユーザーが登録した装填状態の 1 スロット."""

    slot: int = Field(ge=1, le=AMS_SLOT_COUNT)
    product: str
    color: str


class AmsState(BaseModel):
    """ユーザーの AMS の現在の装填状態."""

    connected: bool = False
    slots: list[LoadedSlot] = Field(default_factory=list)

    def find(self, product: str, color: str) -> LoadedSlot | None:
        for slot in self.slots:
            if slot.product == product and slot.color == color:
                return slot
        return None


class SlotAssignment(BaseModel):
    """どのスロットにどのパーツを割り当てるか."""

    slot: int | None
    """装填済みのスロット番号。未装填なら None。"""

    part: str
    product: str
    color: str
    grams: float
    reason: str

    needs_loading: bool = False
    """True なら、このフィラメントを新たに装填する必要がある。"""

    external_spool: bool = False
    """True なら AMS を通せないので外部スプールから給送する。"""


class AmsPlan(BaseModel):
    """STEP6 の成果物."""

    assignments: list[SlotAssignment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def requires_loading(self) -> bool:
        return any(a.needs_loading for a in self.assignments)
