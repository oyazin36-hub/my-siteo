"""機構ルート: パラメトリック CAD による寸法保証つき生成.

画像から起こす装飾ルートと違い、こちらは**外形寸法が企画値に一致することを
検証してから合格とする**。一致しなければ、ずれの実測値を添えて作り直させる。
検証を通ったものだけ dimensional_accuracy=guaranteed になる。
"""

from __future__ import annotations

from dataclasses import dataclass

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
        """寸法が一致するまで作り直す。最後まで合わなければ例外."""
        target = (
            proposal.size_mm.width,
            proposal.size_mm.depth,
            proposal.size_mm.height,
        )

        previous_code: str | None = None
        actual: tuple[float, float, float] | None = None

        for attempt in range(1, self._max_attempts + 1):
            source = await self._codegen.generate(
                proposal, previous_code=previous_code, actual_size_mm=actual
            )
            stl_bytes = await self._renderer.render_stl(source)

            # 装飾ルートと同じ後処理を通す。ただし拡縮はしない。
            # ここで縮めてしまうと、CAD が出した正しい寸法を壊すことになる。
            processed = meshproc.process(MeshArtifact(data=stl_bytes, format="stl"))
            actual = processed.report.size_mm

            if self._matches(target, actual):
                return CadResult(
                    stl=processed.stl,
                    glb=processed.glb,
                    source_code=source,
                    report=processed.report,
                    attempts=attempt,
                )

            previous_code = source

        assert actual is not None
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
    "OpenScadError",
]
