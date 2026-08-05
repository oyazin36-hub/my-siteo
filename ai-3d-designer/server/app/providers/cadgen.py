"""CAD コード生成プロバイダ.

DESIGN.md のとおり、機構ルートの CAD コード生成には Claude を使う
(コード生成の精度が高いため)。企画生成の OpenAI とは別系統。
"""

from __future__ import annotations

from typing import Protocol

from app.domain.models import Proposal
from app.providers.cad_prompts import CAD_SYSTEM_PROMPT, build_cad_prompt, strip_code_fence


class CadGenerationError(Exception):
    pass


class CadCodeProvider(Protocol):
    async def generate(
        self,
        proposal: Proposal,
        *,
        previous_code: str | None = None,
        actual_size_mm: tuple[float, float, float] | None = None,
    ) -> str:
        """OpenSCAD のコードを返す."""
        ...


class ClaudeCadProvider:
    """Claude で OpenSCAD コードを生成する."""

    def __init__(self, api_key: str, model: str = "claude-opus-5") -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(
        self,
        proposal: Proposal,
        *,
        previous_code: str | None = None,
        actual_size_mm: tuple[float, float, float] | None = None,
    ) -> str:
        prompt = build_cad_prompt(proposal, previous_code, actual_size_mm)

        try:
            # 出力が長くなりうるのでストリーミングで受ける(HTTP タイムアウト回避)。
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=CAD_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = await stream.get_final_message()
        except Exception as exc:
            raise CadGenerationError(f"CADコードの生成に失敗しました: {exc}") from exc

        if message.stop_reason == "refusal":
            raise CadGenerationError("CADコードの生成が拒否されました")

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        if not text.strip():
            raise CadGenerationError("CADコードが空でした")

        return strip_code_fence(text)


class StubCadProvider:
    """API キーなしで開発・テストするためのスタブ.

    企画の外形寸法をそのまま満たす、フタ付きケースの形状を返す。
    実際の設計ではないが、**寸法が指定どおりに出る**ことは本物と同じなので、
    寸法検証ループの検証に使える。
    """

    async def generate(
        self,
        proposal: Proposal,
        *,
        previous_code: str | None = None,
        actual_size_mm: tuple[float, float, float] | None = None,
    ) -> str:
        size = proposal.size_mm
        return f"""\
// {proposal.product_name}
// 自動生成(スタブ)。外形は企画値に一致させてある。

width  = {size.width};
depth  = {size.depth};
height = {size.height};
wall   = 2.0;   // 壁の厚み

// 外殻から内側をくり抜いたケース。上面は開口。
difference() {{
    cube([width, depth, height]);

    translate([wall, wall, wall])
        cube([width - 2 * wall, depth - 2 * wall, height]);
}}
"""
