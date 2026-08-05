"""機構ルート(パラメトリック CAD)のプロンプト."""

from __future__ import annotations

from app.domain.models import Proposal

CAD_SYSTEM_PROMPT = """\
あなたは3Dプリント用のパラメトリック CAD 設計者です。
与えられた企画から、OpenSCAD のコードを1つ書いてください。

## 絶対に守ること

1. **外形寸法を指定値に正確に一致させること。**
   完成形状のバウンディングボックスが、指定された 幅 x 奥行 x 高さ に
   ぴったり一致しなければなりません。この寸法が要件そのものです。
2. **形状は第一象限に置くこと。** 原点 (0,0,0) を最小角として、
   X/Y/Z がすべて 0 以上の範囲に収まるようにしてください。
3. **閉じた立体(防水)にすること。** 面の抜けや厚みゼロの部分を作らないでください。
4. **ファイルを読む命令は使用禁止です。**
   include / use / import / surface は使えません。これらを書くと実行が拒否されます。
   すべて1つのコード内で完結させてください。

## 3Dプリントの制約

- オーバーハングは45度以内。サポート材が要らない形状を優先してください
- 壁の厚みは最低 1.2mm(ノズル径0.4mmの3周ぶん)
- 可動部のすきまは 0.2〜0.3mm 確保してください
- バネが必要な場合は金属部品を使わず、細い梁のたわみを使った板バネとして
  一体成形してください
- 穴は上向きに開けると天井が垂れます。造形の向きを考慮してください

## コードの書き方

- 冒頭に寸法パラメータを変数としてまとめてください(後から調整できるように)
- 各パーツが何であるかをコメントで示してください
- $fn は 32〜64 程度にしてください(大きすぎると描画に時間がかかります)

## 出力形式

OpenSCAD のコードだけを出力してください。
説明文やマークダウンのコードフェンスは付けないでください。
"""


def build_cad_prompt(
    proposal: Proposal,
    previous_code: str | None = None,
    actual_size_mm: tuple[float, float, float] | None = None,
) -> str:
    """初回生成と、寸法が合わなかったときの再生成の両方で使う."""
    size = proposal.size_mm
    sections = [
        "# 企画",
        f"商品名: {proposal.product_name}",
        f"概要: {proposal.concept}",
        f"**外形寸法(必達): 幅 {size.width}mm x 奥行 {size.depth}mm x 高さ {size.height}mm**",
    ]
    if proposal.capacity:
        sections.append(f"収納: {proposal.capacity}")
    if proposal.mechanism:
        sections.append(f"機構: {proposal.mechanism}")
    sections.append(f"素材: {proposal.material}")
    if proposal.features:
        sections.append("設計の要点:\n" + "\n".join(f"- {f}" for f in proposal.features))

    if previous_code is not None and actual_size_mm is not None:
        # 寸法が外れたときは、何がどうずれたかを具体的に返す。
        # 「直して」だけでは同じ間違いを繰り返しやすい。
        sections.append(
            "\n# 前回のコード\n"
            f"```\n{previous_code}\n```\n"
            "\n# 問題\n"
            "レンダリング結果の外形が "
            f"{actual_size_mm[0]:.2f} x {actual_size_mm[1]:.2f} x {actual_size_mm[2]:.2f} mm "
            f"となり、指定の {size.width} x {size.depth} x {size.height} mm と"
            "一致しませんでした。\n"
            "外形が指定値にぴったり一致するよう修正したコードを出力してください。"
            "形状の意図は保ったまま、寸法だけを合わせてください。"
        )

    return "\n".join(sections)


def strip_code_fence(text: str) -> str:
    """モデルがコードフェンスを付けてきた場合に取り除く."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    # 先頭の ``` または ```openscad と、末尾の ``` を落とす
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
