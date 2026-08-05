"""STEP5-6: 印刷データ(3MF)の生成と印刷条件の算出."""

from __future__ import annotations

from app.domain.models import PrintData, Project, ProjectStatus
from app.providers.slicer import Slicer, SlicerError
from app.providers.storage import BlobStorage
from app.repositories.base import ProjectRepository
from app.services import threemf
from app.services.design import InvalidStateError


class PrintingService:
    def __init__(
        self,
        *,
        repository: ProjectRepository,
        storage: BlobStorage,
        slicer: Slicer,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._slicer = slicer

    async def build(self, project: Project) -> Project:
        """3D モデルの STL から 3MF を作り、印刷条件を算出する."""
        if project.status is not ProjectStatus.model_review or project.model is None:
            raise InvalidStateError(project.status, "印刷データの生成")
        if not project.model.printable or project.model.url is None:
            # 壊れたモデルから印刷データを作らせない。
            raise InvalidStateError(project.status, "印刷データの生成")

        stl_bytes = await self._storage.get(project.model.url)

        assert project.proposal is not None
        proposal = project.proposal

        project.status = ProjectStatus.slicing
        await self._repo.save(project)

        archive = threemf.from_mesh(
            stl_bytes,
            threemf.ThreeMfMetadata(
                title=proposal.product_name,
                description=(
                    f"{proposal.concept} / 外形 {proposal.size_mm.as_text()}"
                    f" / 推奨素材 {proposal.material}"
                ),
            ),
        )

        url = await self._storage.put(project_id=project.id, data=archive, media_type="model/3mf")

        warnings: list[str] = [
            "プリンタとフィラメントのプリセットは Bambu Studio 側で選んでください。"
            "3MF には形状のみを入れています。",
            "造形の向きとサポート材の要否は Bambu Studio で最終確認してください。",
        ]

        try:
            estimate = await self._slicer.estimate(
                model_bytes=archive, material=proposal.material, filename="model.3mf"
            )
        except SlicerError as exc:
            # 見積れなくても 3MF は渡せる。数値を捏造せず、出せない旨を伝える。
            project.print_data = PrintData(
                url=url,
                material=proposal.material,
                estimated=True,
                estimate_source="見積り不可",
                warnings=[*warnings, f"印刷時間と使用量を算出できませんでした: {exc}"],
            )
        else:
            if estimate.estimated:
                warnings.append(
                    "印刷時間と使用量は体積からの概算です。"
                    "正確な値は Bambu Studio でスライスして確認してください。"
                )
            project.print_data = PrintData(
                url=url,
                material=proposal.material,
                print_time_min=estimate.print_time_min,
                filament_grams=estimate.filament_grams,
                estimated=estimate.estimated,
                estimate_source=estimate.source,
                warnings=warnings,
            )

        project.status = ProjectStatus.print_ready
        return await self._repo.save(project)
