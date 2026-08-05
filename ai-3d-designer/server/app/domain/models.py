"""ドメインモデル.

Firestore のドキュメント構造と 1:1 に対応する。
構造の全体像は docs/ai-3d-product-designer/DESIGN.md §4 を参照。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(StrEnum):
    """プロジェクトの状態機械.

    idea_input → proposing → proposal_review ⇄ (修正)
               → image_generating → image_review ⇄ (修正)
               → model_generating → model_review ⇄ (修正)
               → slicing → print_ready

    Phase 1 で扱うのは image_review まで。
    """

    idea_input = "idea_input"
    proposing = "proposing"
    proposal_review = "proposal_review"
    image_generating = "image_generating"
    image_review = "image_review"
    model_generating = "model_generating"
    model_review = "model_review"
    slicing = "slicing"
    print_ready = "print_ready"


class DesignRoute(StrEnum):
    """生成ルート。DESIGN.md §0 の 2 ルート方式."""

    decorative = "decorative"
    """見た目もの。画像 → 3D生成API。寸法は保証しない。"""

    mechanism = "mechanism"
    """寸法と機構が要るもの。LLM + パラメトリック CAD。寸法を mm 単位で保証する。"""


class ImageKind(StrEnum):
    exterior = "exterior"
    scene = "scene"
    exploded = "exploded"
    internal = "internal"
    dimensions = "dimensions"


class Idea(BaseModel):
    """STEP1: ユーザーの入力."""

    text: str = Field(min_length=1, max_length=4000)
    image_urls: list[str] = Field(default_factory=list, max_length=8)


class Dimensions(BaseModel):
    """外形寸法 (mm)."""

    width: float = Field(gt=0, le=256)
    depth: float = Field(gt=0, le=256)
    height: float = Field(gt=0, le=256)

    def as_text(self) -> str:
        return f"{self.width:g} x {self.depth:g} x {self.height:g} mm"


class Revision(BaseModel):
    """修正ループ 1 回分の記録."""

    request: str
    applied_at: datetime = Field(default_factory=_now)


class Proposal(BaseModel):
    """STEP2: AI の企画提案."""

    product_name: str
    concept: str
    size_mm: Dimensions
    capacity: str | None = None
    mechanism: str | None = None
    material: str
    print_time_est_min: int = Field(gt=0)
    features: list[str] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)


class GeneratedImage(BaseModel):
    """STEP3: 生成された画像 1 枚."""

    kind: ImageKind
    url: str
    prompt: str
    created_at: datetime = Field(default_factory=_now)


class Project(BaseModel):
    """1 作品 = 1 プロジェクト."""

    id: str
    owner_uid: str
    title: str = "無題のプロジェクト"
    status: ProjectStatus = ProjectStatus.idea_input
    route: DesignRoute | None = None
    idea: Idea
    proposal: Proposal | None = None
    images: list[GeneratedImage] = Field(default_factory=list)
    image_revisions: list[Revision] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()
