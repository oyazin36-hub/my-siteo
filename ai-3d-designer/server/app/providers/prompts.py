"""LLM に渡すプロンプト.

プロバイダ実装から分離してあるので、プロンプトだけを単体でレビュー・テストできる。
"""

from __future__ import annotations

from app.domain.models import Idea, Proposal

PROPOSAL_SYSTEM_PROMPT = """\
あなたは3Dプリント商品の設計者です。ユーザーの要望から、Bambu Lab P2S で印刷できる
商品の企画を1つ立ててください。ユーザーはCADの知識を持っていません。

## 生成ルートの判定
まず route を判定してください。これは後工程の3Dモデル生成方式を決めます。

- mechanism: 寸法や機構が成立している必要があるもの。
  ケース・スタンド・ホルダー・箱・可動部を持つものなど。
  「30枚入る」「ポケットに入る」のような寸法制約が要望に含まれる場合もこちら。
- decorative: 見た目が主目的のもの。フィギュア・置物・装飾品など。
  寸法の厳密さが要求されないもの。

判断に迷う場合は mechanism を選んでください。寸法が保証される経路のためです。

## 寸法の決め方
- 収納物がある場合、その規格寸法から逆算してください
  (例: 日本の名刺は 91 x 55 mm、クレジットカードは 85.6 x 54 mm)
- 収納枚数が指定された場合、紙1枚を約0.23mmとして束の厚みを見積もってください
- 「ポケットに入る」は概ね 100 x 70 x 20 mm 以内を目安にしてください
- P2S の造形範囲は 256 x 256 x 256 mm です。これを超えてはいけません

## 印刷可能性の制約
- サポート材が不要な形状を優先してください(オーバーハングは45度以内)
- バネなどの弾性部品は、金属部品を使わず板バネとして一体成形してください
- 素材は Bambu Lab 純正フィラメントから選んでください
  (PLA Basic / PETG Basic / ABS / TPU など)。弾性や耐久が要る部品は PETG を検討してください

## 出力
- product_name は日本語で、製品名として自然なものにしてください
- concept はその製品が何で、どう使うものかを2〜3文で説明してください
- features は設計上の要点を3〜5個、簡潔に挙げてください
- print_time_est_min は 0.2mm 積層で P2S で印刷した場合の目安を分単位で答えてください
"""


def build_proposal_prompt(
    idea: Idea,
    current: Proposal | None = None,
    revision_request: str | None = None,
) -> str:
    """初回生成と修正の両方でこの関数を使う。current が None なら初回."""
    sections = [f"# ユーザーの要望\n{idea.text}"]

    if idea.image_urls:
        sections.append(
            f"# 添付画像\n{len(idea.image_urls)}枚の参考画像が添付されています。"
            "外観の参考にしてください。"
        )

    if current is not None and revision_request is not None:
        sections.append(
            "# 現在の企画\n"
            f"- 商品名: {current.product_name}\n"
            f"- コンセプト: {current.concept}\n"
            f"- サイズ: {current.size_mm.as_text()}\n"
            f"- 収納: {current.capacity or '(なし)'}\n"
            f"- 機構: {current.mechanism or '(なし)'}\n"
            f"- 素材: {current.material}\n"
            f"- 印刷時間: 約{current.print_time_est_min}分\n"
            f"- 特徴: {', '.join(current.features) if current.features else '(なし)'}"
        )
        sections.append(
            "# 修正指示\n"
            f"{revision_request}\n\n"
            "この指示を反映した企画を出力してください。"
            "**指示された点だけを変更し、それ以外は現在の企画を維持してください。**"
            "変更が他の項目に波及する場合(例: 薄くすると収納枚数が減る)は、"
            "その項目も整合するように調整し、features にその旨を含めてください。"
        )

    return "\n\n".join(sections)


# --- 画像生成 ---

_SHARED_IMAGE_RULES = (
    "背景は無地の白。被写体は1点のみ。文字やロゴ、透かし、寸法線以外の注釈は入れない。"
    "写実的なプロダクト写真のスタイル。"
)


def build_image_prompt(proposal: Proposal, kind: str) -> str:
    """3D化を見据えて「単一オブジェクト・背景なし」を固定で強制する.

    DESIGN.md §5 のリスク1(装飾ルートの品質ばらつき)への対策。
    後段の画像→3D生成の入力品質はここでほぼ決まる。
    """
    base = (
        f"3Dプリント製品「{proposal.product_name}」。"
        f"{proposal.concept} "
        f"外形寸法は {proposal.size_mm.as_text()}。素材は{proposal.material}。"
    )

    per_kind = {
        "exterior": (
            f"{base} 製品全体を斜め45度から見た外観。{_SHARED_IMAGE_RULES} "
            "製品が画面中央に収まり、全体が途切れず写っていること。"
        ),
        "scene": (
            f"{base} この製品を実際に使用している場面。手に持って使っている様子。"
            "背景は生活感のある自然な環境。"
        ),
        "exploded": (
            f"{base} 分解図。各パーツが上下に間隔をあけて配置され、"
            f"組み立て順が分かる図。{_SHARED_IMAGE_RULES}"
        ),
        "internal": (
            f"{base} 内部構造が分かる断面図。"
            f"{proposal.mechanism or '内部の構成'}が見えるように断面で示す。"
            f"{_SHARED_IMAGE_RULES}"
        ),
        "dimensions": (
            f"{base} 寸法図。正面図と側面図を並べ、寸法線と数値を記入した"
            f"テクニカルドローイング風の図。{_SHARED_IMAGE_RULES}"
        ),
    }

    if kind not in per_kind:
        raise ValueError(f"未知の画像種別: {kind}")
    return per_kind[kind]


def build_image_revision_prompt(proposal: Proposal, kind: str, revision_request: str) -> str:
    return f"{build_image_prompt(proposal, kind)}\n\n追加の指示: {revision_request}"
