"""機構ルート: パラメトリック CAD による寸法保証つき生成.

画像から起こす装飾ルートと違い、こちらは**外形寸法が企画値に一致することを
検証してから合格とする**。一致しなければ、ずれの実測値を添えて作り直させる。
検証を通ったものだけ dimensional_accuracy=guaranteed になる。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import feasibility
from app.domain.models import Proposal
from app.providers.cadgen import CadCodeProvider, CadGenerationError
from app.providers.mesh3d import MeshArtifact
from app.providers.openscad import OpenScadError, OpenScadRenderer
from app.services import meshproc

#: 実寸が企画値からこの範囲に収まっていれば合格 (mm)。
#: 0.1mm はノズル径 0.4mm の 1/4 で、印刷では現れない差。
DIMENSION_TOLERANCE_MM = 0.1

#: 寸法が合うまで作り直す回数の上限。
MAX_ATTEMPTS = 3


@dataclass
class CadResult:
    stl: bytes
    glb: bytes
    source_code: str
    report: meshproc.MeshReport
    attempts: int
    """何回目で寸法が一致したか。"""


class DimensionMismatchError(Exception):
    """規定回数試しても外形が企画値に一致しなかった."""

    def __init__(self, target: tuple[float, float, float], actual: tuple[float, float, float]):
        super().__init__(
            f"外形寸法を企画値に一致させられませんでした。"
            f"目標 {target[0]}x{target[1]}x{target[2]}mm に対し "
            f"実測 {actual[0]:.2f}x{actual[1]:.2f}x{actual[2]:.2f}mm"
        )
        self.target = target
        self.actual = actual


class NoRoomForContentsError(Exception):
    """外形は一致したが、収納物が入る空間が内部に無かった.

    外形だけ合わせて中身が入らない物を「寸法保証つき」と言わないための例外。
    """


class CadService:
    def __init__(
        self,
        *,
        code_provider: CadCodeProvider,
        renderer: OpenScadRenderer,
        tolerance_mm: float = DIMENSION_TOLERANCE_MM,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._codegen = code_provider
        self._renderer = renderer
        self._tolerance = tolerance_mm
        self._max_attempts = max_attempts

    async def build(self, proposal: Proposal) -> CadResult:
        """寸法が一致し、収納物が入るまで作り直す。最後まで駄目なら例外."""
        target = (
            proposal.size_mm.width,
            proposal.size_mm.depth,
            proposal.size_mm.height,
        )
        # 収納物が読み取れる企画なら、外形だけでなく中身の入る空間も見る。
        content_box = feasibility.required_content_box_mm(proposal)

        previous_code: str | None = None
        actual: tuple[float, float, float] | None = None
        hollow_failure: str | None = None

        for attempt in range(1, self._max_attempts + 1):
            source = await self._codegen.generate(
                proposal, previous_code=previous_code, actual_size_mm=actual
            )
            stl_bytes = await self._renderer.render_stl(source)

            # 装飾ルートと同じ後処理を通す。ただし拡縮はしない。
            # ここで縮めてしまうと、CAD が出した正しい寸法を壊すことになる。
            processed = meshproc.process(
                MeshArtifact(data=stl_bytes, format="stl"), content_box_mm=content_box
            )
            actual = processed.report.size_mm
            previous_code = source

            if not self._matches(target, actual):
                hollow_failure = None
                continue

            # 外形が合っていても中が詰まっていることがある。
            # content_fits が None(判定できず)は落とさない。
            # 判定できないことを不合格の理由にすると、作り直しても直らない。
            if processed.report.content_fits is False:
                assert content_box is not None
                hollow_failure = (
                    f"外形は一致したが、収納物 "
                    f"{content_box[0]:.0f}x{content_box[1]:.0f}x{content_box[2]:.1f}mm "
                    f"の入る空間が内部にない"
                )
                continue

            return CadResult(
                stl=processed.stl,
                glb=processed.glb,
                source_code=source,
                report=processed.report,
                attempts=attempt,
            )

        assert actual is not None
        if hollow_failure is not None:
            raise NoRoomForContentsError(hollow_failure)
        raise DimensionMismatchError(target, actual)

    def _matches(
        self, target: tuple[float, float, float], actual: tuple[float, float, float]
    ) -> bool:
        return all(abs(a - t) <= self._tolerance for t, a in zip(target, actual, strict=True))


__all__ = [
    "CadGenerationError",
    "CadResult",
    "CadService",
    "DimensionMismatchError",
    "NoRoomForContentsError",
    "OpenScadError",
]
