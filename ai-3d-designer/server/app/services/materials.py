"""STEP5-6: フィラメント選定と AMS スロット配置.

役割分担:
- パーツ分解と要件の判断 … LLM (providers/parts.py)
- 要件からフィラメントを選ぶ … 決定的なルール (domain/filaments.py)
- スロットへの割り当て … このモジュール
"""

from __future__ import annotations

from app.domain.ams import AMS_SLOT_COUNT, AmsPlan, AmsState, SlotAssignment
from app.domain.filaments import (
    NoSuitableFilamentError,
    PartRequirement,
    select,
)
from app.domain.models import Proposal
from app.providers.parts import PartsDecomposer


class MaterialsService:
    def __init__(self, *, decomposer: PartsDecomposer) -> None:
        self._decomposer = decomposer

    async def plan(
        self,
        proposal: Proposal,
        *,
        total_grams: float,
        ams: AmsState | None = None,
    ) -> AmsPlan:
        requirements = await self._decomposer.decompose(proposal)
        return self.plan_for_requirements(requirements, total_grams=total_grams, ams=ams)

    def plan_for_requirements(
        self,
        requirements: list[PartRequirement],
        *,
        total_grams: float,
        ams: AmsState | None = None,
    ) -> AmsPlan:
        state = ams or AmsState()
        assignments: list[SlotAssignment] = []
        warnings: list[str] = []

        # 未装填のフィラメントに割り当てる空きスロット。
        used_slots = {slot.slot for slot in state.slots}
        free_slots = [n for n in range(1, AMS_SLOT_COUNT + 1) if n not in used_slots]

        # 同じフィラメント(製品+色)を要求するパーツは 1 スロットを共有する。
        # 分けるとスロットを無駄に消費し、4 色までしか使えなくなる。
        proposed_slots: dict[tuple[str, str], int | None] = {}

        for requirement in requirements:
            try:
                filament, color, reason = select(requirement)
            except NoSuitableFilamentError as exc:
                # 選べないものを黙って別のもので埋めない。
                warnings.append(str(exc))
                continue

            grams = round(total_grams * requirement.volume_ratio, 1)

            if not filament.ams_compatible:
                assignments.append(
                    SlotAssignment(
                        slot=None,
                        part=requirement.name,
                        product=filament.product,
                        color=color,
                        grams=grams,
                        reason=reason,
                        external_spool=True,
                    )
                )
                continue

            loaded = state.find(filament.product, color)
            if loaded is not None:
                assignments.append(
                    SlotAssignment(
                        slot=loaded.slot,
                        part=requirement.name,
                        product=filament.product,
                        color=color,
                        grams=grams,
                        reason=reason,
                    )
                )
                continue

            # 装填されていないので、空きスロットへの装填を提案する。
            key = (filament.product, color)
            if key in proposed_slots:
                slot = proposed_slots[key]  # 同じフィラメントなので同じスロット
                already_warned = True
            else:
                slot = free_slots.pop(0) if free_slots else None
                proposed_slots[key] = slot
                already_warned = False

            assignments.append(
                SlotAssignment(
                    slot=slot,
                    part=requirement.name,
                    product=filament.product,
                    color=color,
                    grams=grams,
                    reason=reason,
                    needs_loading=True,
                )
            )
            if slot is None and not already_warned:
                warnings.append(
                    f"「{requirement.name}」に必要な {filament.product}({color}) を入れる"
                    f"AMS の空きスロットがありません。どれかを入れ替えるか、"
                    f"パーツをまとめて色数を減らしてください。"
                )

        self._add_summary_warnings(state, assignments, warnings)
        return AmsPlan(assignments=assignments, warnings=warnings)

    def _add_summary_warnings(
        self,
        state: AmsState,
        assignments: list[SlotAssignment],
        warnings: list[str],
    ) -> None:
        if not state.connected:
            warnings.append(
                "AMS の装填状態が未登録です。下記は「何を入れるとよいか」の提案です。"
                "設定から実際の装填内容を登録すると、入れ替えの要否まで分かります。"
            )
        elif any(a.needs_loading for a in assignments):
            missing = ", ".join(f"{a.product}({a.color})" for a in assignments if a.needs_loading)
            warnings.append(f"未装填のフィラメントがあります: {missing}")

        if any(a.external_spool for a in assignments):
            warnings.append(
                "AMS を通せないフィラメントが含まれます。該当パーツは外部スプールから"
                "給送し、別々に印刷してください。"
            )

        distinct = {(a.product, a.color) for a in assignments}
        if len(distinct) > 1:
            warnings.append(
                f"{len(distinct)} 色を使う構成です。色替えのたびにフィラメントを"
                "パージするため、材料と時間が余分にかかります。"
            )
