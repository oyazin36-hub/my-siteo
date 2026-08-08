"""パーツ分解プロバイダ.

製品をパーツに分けて、各パーツに必要な性質(強度・柔軟性・耐熱・色)を出す。
**ここまでが LLM の仕事**で、その要件からどのフィラメントを選ぶかは
``app.domain.filaments.select`` が決定的に行う。

分けている理由: 選定まで LLM に任せると同じ入力で結果が揺れ、
「なぜこれが選ばれたか」も後から説明できなくなる。
"""

from __future__ import annotations

from typing import Protocol

from app.domain.filaments import PartRequirement, Strength
from app.domain.models import Proposal

PARTS_SYSTEM_PROMPT = """\
あなたは3Dプリント製品の製造設計者です。
与えられた企画を、印刷するパーツに分解してください。

## 各パーツについて答えること

- name: パーツ名(例: 本体、フタ、ボタン、板バネ、ロゴ)
- role: そのパーツの役目を一言で
- min_strength: 必要な強度 (low / medium / high)
    - low:    力がかからない装飾やロゴ
    - medium: 繰り返し曲がる、はめ合う、荷重がかかる
    - high:   工具のように強い力がかかる、割れると危険
- needs_flexibility: ゴムのように曲がる必要があるか (true / false)
    - 板バネは「たわむ」だけなので false。ゴム足やパッキンが true
- min_heat_resist_c: 必要な耐熱温度(℃)。屋内で使うだけなら 0
    - 夏の車内に置く可能性があるなら 80 以上
- preferred_color: 色の希望があれば。なければ null
- volume_ratio: 全体の材料量に占める割合(0〜1)。合計が 1 になるようにする

## 注意

- 色分けの必要がない製品なら、パーツは 1 つで構いません。無理に分けないでください
- 過剰な要件を付けないでください。強度や耐熱を上げるほど印刷が難しくなります
"""


class PartsDecomposer(Protocol):
    async def decompose(self, proposal: Proposal) -> list[PartRequirement]: ...


class ClaudePartsDecomposer:
    """Claude にパーツ分解させる."""

    def __init__(self, api_key: str, model: str = "claude-opus-5") -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def decompose(self, proposal: Proposal) -> list[PartRequirement]:
        from app.providers.cadgen import CadGenerationError

        prompt = (
            f"# 企画\n"
            f"商品名: {proposal.product_name}\n"
            f"概要: {proposal.concept}\n"
            f"外形: {proposal.size_mm.as_text()}\n"
            f"機構: {proposal.mechanism or 'なし'}\n"
            f"推奨素材: {proposal.material}\n"
            + ("設計の要点:\n" + "\n".join(f"- {f}" for f in proposal.features))
            if proposal.features
            else ""
        )

        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=4000,
                thinking={"type": "adaptive"},
                system=PARTS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "parts": {
                                    "type": "array",
                                    "items": _PART_SCHEMA,
                                }
                            },
                            "required": ["parts"],
                            "additionalProperties": False,
                        },
                    }
                },
            )
        except Exception as exc:
            raise CadGenerationError(f"パーツ分解に失敗しました: {exc}") from exc

        import json

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        payload = json.loads(text)
        return [PartRequirement.model_validate(item) for item in payload["parts"]]


_PART_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "min_strength": {"type": "integer", "enum": [1, 2, 3]},
        "needs_flexibility": {"type": "boolean"},
        "min_heat_resist_c": {"type": "integer"},
        "preferred_color": {"type": ["string", "null"]},
        "volume_ratio": {"type": "number"},
    },
    "required": [
        "name",
        "role",
        "min_strength",
        "needs_flexibility",
        "min_heat_resist_c",
        "preferred_color",
        "volume_ratio",
    ],
    "additionalProperties": False,
}


class StubPartsDecomposer:
    """API キーなしで開発・テストするためのスタブ.

    企画の機構と特徴から、ごく単純にパーツを推定する。
    """

    async def decompose(self, proposal: Proposal) -> list[PartRequirement]:
        text = f"{proposal.concept} {proposal.mechanism or ''} {' '.join(proposal.features)}"

        parts: list[PartRequirement] = [
            PartRequirement(
                name="本体",
                role="製品の主要部",
                min_strength=Strength.medium if _has_mechanism(text) else Strength.low,
                preferred_color="Black",
                volume_ratio=0.8 if _has_mechanism(text) else 1.0,
            )
        ]

        if "バネ" in text or "ヒンジ" in text:
            parts.append(
                PartRequirement(
                    name="板バネ",
                    role="繰り返したわませる部分",
                    min_strength=Strength.medium,
                    preferred_color="Black",
                    volume_ratio=0.05,
                )
            )
        if "ボタン" in text:
            parts.append(
                PartRequirement(
                    name="ボタン",
                    role="操作する部分。色を分けて見つけやすくする",
                    min_strength=Strength.low,
                    preferred_color="Orange",
                    volume_ratio=0.05,
                )
            )
        if "窓" in text or "ロゴ" in text:
            parts.append(
                PartRequirement(
                    name="ロゴ",
                    role="装飾",
                    min_strength=Strength.low,
                    preferred_color="White",
                    volume_ratio=0.02,
                )
            )

        return _normalise_ratios(parts)


def _has_mechanism(text: str) -> bool:
    return any(word in text for word in ("ボタン", "バネ", "ヒンジ", "スライド", "はめ"))


def _normalise_ratios(parts: list[PartRequirement]) -> list[PartRequirement]:
    """合計が 1 になるよう按分する。使用量の割り振りに使うため."""
    total = sum(part.volume_ratio for part in parts)
    if total <= 0:
        return parts
    return [part.model_copy(update={"volume_ratio": part.volume_ratio / total}) for part in parts]
