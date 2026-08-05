"""LLM プロバイダ.

Phase 1 の実装は OpenAI。Phase 3 の CAD コード生成では Claude の併用を想定しているため、
呼び出し側がプロバイダを意識しないようプロトコルで抽象化してある。
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.models import DesignRoute, Dimensions, Idea, Proposal
from app.providers.prompts import PROPOSAL_SYSTEM_PROMPT, build_proposal_prompt


class ProposalDraft(BaseModel):
    """LLM が返す企画。Proposal との違いは revisions を持たないこと."""

    route: DesignRoute
    product_name: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    size_mm: Dimensions
    capacity: str | None = None
    mechanism: str | None = None
    material: str = Field(min_length=1)
    print_time_est_min: int = Field(gt=0, le=60 * 24 * 7)
    features: list[str] = Field(default_factory=list)


class LLMError(Exception):
    """LLM の呼び出しに失敗した、または出力が想定の形式でなかった."""


class LLMProvider(Protocol):
    async def draft_proposal(
        self,
        *,
        idea: Idea,
        current: Proposal | None = None,
        revision_request: str | None = None,
    ) -> ProposalDraft: ...


class OpenAILLMProvider:
    """OpenAI の構造化出力で企画を生成する.

    構造化出力(json_schema)を使うことで、パース失敗のリトライループが不要になる。
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-2024-08-06") -> None:
        # openai は依存が重いので遅延 import。スタブ利用時は未インストールでも動く。
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def draft_proposal(
        self,
        *,
        idea: Idea,
        current: Proposal | None = None,
        revision_request: str | None = None,
    ) -> ProposalDraft:
        user_prompt = build_proposal_prompt(idea, current, revision_request)

        content: list[dict[str, object]] = [{"type": "text", "text": user_prompt}]
        for url in idea.image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})

        try:
            completion = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": PROPOSAL_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                response_format=ProposalDraft,
            )
        except Exception as exc:
            raise LLMError(f"企画の生成に失敗しました: {exc}") from exc

        draft = completion.choices[0].message.parsed
        if draft is None:
            # 安全フィルタなどで拒否された場合。呼び出し側が 502 に変換する。
            refusal = completion.choices[0].message.refusal
            raise LLMError(f"企画を生成できませんでした: {refusal or '応答が空です'}")
        return draft


class StubLLMProvider:
    """API キーなしで開発・テストするためのスタブ.

    要望文から寸法や収納数をごく単純に読み取り、それらしい企画を返す。
    修正指示は「薄く」「大きく」など代表的な語だけに反応する。
    実在の LLM の代替ではなく、フロー全体を通すための足場。
    """

    def __init__(self) -> None:
        self._counter = 0

    async def draft_proposal(
        self,
        *,
        idea: Idea,
        current: Proposal | None = None,
        revision_request: str | None = None,
    ) -> ProposalDraft:
        self._counter += 1

        if current is not None and revision_request is not None:
            return self._revise(current, revision_request)
        return self._initial(idea)

    def _initial(self, idea: Idea) -> ProposalDraft:
        text = idea.text
        capacity_match = re.search(r"(\d+)\s*枚", text)
        capacity_count = int(capacity_match.group(1)) if capacity_match else None

        is_card_case = any(word in text for word in ("名刺", "カード", "ケース", "入れ"))
        route = DesignRoute.mechanism if _looks_mechanical(text) else DesignRoute.decorative

        if is_card_case:
            # 名刺 91x55mm + 束の厚み(1枚 0.23mm)から逆算する。
            stack = (capacity_count or 30) * 0.23
            return ProposalDraft(
                route=route,
                product_name="スマートスライド名刺ケース",
                concept=(
                    "普段はフタの窓から名刺の面が見えるフラットなケース。"
                    "前面のボタンを押すとフタが開き、名刺の先端が扇状に持ち上がって"
                    "1枚ずつ取り出せます。"
                ),
                size_mm=Dimensions(width=96, depth=60, height=round(stack + 6.5, 1)),
                capacity=f"名刺{capacity_count or 30}枚",
                mechanism="ボタン式スライド排出",
                material="Bambu PETG Basic",
                print_time_est_min=180,
                features=[
                    "窓付きフタで一番上の名刺が見える",
                    "板バネを一体成形し金属部品を使わない",
                    "サポート材不要の造形向き",
                    "4パーツ構成",
                ],
            )

        return ProposalDraft(
            route=route,
            product_name=f"カスタム3Dプリント品 {self._counter}",
            concept=f"「{text[:40]}」という要望から起こした試作案です。",
            size_mm=Dimensions(width=80, depth=80, height=40),
            capacity=f"{capacity_count}個" if capacity_count else None,
            mechanism="なし" if route is DesignRoute.decorative else "未定",
            material="Bambu PLA Basic",
            print_time_est_min=90,
            features=["サポート材不要の造形向き", "単一パーツ"],
        )

    def _revise(self, current: Proposal, request: str) -> ProposalDraft:
        size = current.size_mm.model_copy()
        features = list(current.features)

        if any(word in request for word in ("薄く", "薄い", "低く")):
            size.height = max(round(size.height * 0.8, 1), 1.0)
            features.append(f"修正: 厚みを{size.height}mmに変更")
        if any(word in request for word in ("小さく", "コンパクト")):
            size.width = max(round(size.width * 0.9, 1), 1.0)
            size.depth = max(round(size.depth * 0.9, 1), 1.0)
            features.append("修正: 外形を縮小")
        if any(word in request for word in ("大きく", "広く")):
            size.width = min(round(size.width * 1.1, 1), 256.0)
            size.depth = min(round(size.depth * 1.1, 1), 256.0)
            features.append("修正: 外形を拡大")

        if len(features) == len(current.features):
            # 認識できない指示でも記録は残す。無視されたように見せない。
            features.append(f"修正指示を反映: {request[:40]}")

        return ProposalDraft(
            route=DesignRoute.mechanism,
            product_name=current.product_name,
            concept=current.concept,
            size_mm=size,
            capacity=current.capacity,
            mechanism=current.mechanism,
            material=current.material,
            print_time_est_min=current.print_time_est_min,
            features=features,
        )


_MECHANICAL_HINTS = (
    "ケース",
    "入れ",
    "ホルダー",
    "スタンド",
    "箱",
    "ボックス",
    "収納",
    "フック",
    "取り付け",
    "ボタン",
    "mm",
    "枚",
    "サイズ",
)


def _looks_mechanical(text: str) -> bool:
    return any(hint in text for hint in _MECHANICAL_HINTS)
