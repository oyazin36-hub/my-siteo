"""STEP4: 3D モデル生成のオーケストレーション.

3D 生成は数十秒〜数分かかるため非同期で走らせる。クライアントは
プロジェクトを取得して ``model.job_status`` を見る。

Phase 2 では装飾ルート(画像 → 3D生成API)のみを実装している。
機構ルートのプロジェクトもこの経路で暫定のモデルを作るが、
``dimensional_accuracy`` は approximate のままで、寸法保証は Phase 3 で行う。
"""

from __future__ import annotations

import asyncio
import logging

from app.domain.models import (
    DesignRoute,
    DimensionalAccuracy,
    Dimensions,
    JobStatus,
    Model3D,
    Project,
    ProjectStatus,
    Revision,
)
from app.providers.mesh3d import GenerationRequest, Mesh3DError, Mesh3DProvider
from app.providers.storage import BlobStorage
from app.repositories.base import ProjectRepository
from app.services import meshproc
from app.services.design import InvalidStateError

logger = logging.getLogger(__name__)

#: ポーリングの間隔と上限。上限に達したら失敗として扱う。
_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 900.0


class ModelingService:
    def __init__(
        self,
        *,
        repository: ProjectRepository,
        mesh_provider: Mesh3DProvider,
        storage: BlobStorage,
        gen_source: str,
        poll_interval: float = _POLL_INTERVAL_SECONDS,
        poll_timeout: float = _POLL_TIMEOUT_SECONDS,
    ) -> None:
        self._repo = repository
        self._provider = mesh_provider
        self._storage = storage
        self._gen_source = gen_source
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    async def enqueue(self, project: Project, revision_request: str | None = None) -> Project:
        """ジョブを受け付けて即座に返す。実処理は run() で行う."""
        if project.proposal is None or not project.images:
            raise InvalidStateError(project.status, "3Dモデルの生成")

        if revision_request is None:
            if project.status is not ProjectStatus.image_review:
                raise InvalidStateError(project.status, "3Dモデルの生成")
        elif project.status is not ProjectStatus.model_review:
            raise InvalidStateError(project.status, "3Dモデルの修正")

        previous_revisions = list(project.model.revisions) if project.model else []
        if revision_request is not None:
            previous_revisions.append(Revision(request=revision_request))

        project.model = Model3D(
            job_status=JobStatus.queued,
            gen_source=self._gen_source,
            dimensional_accuracy=DimensionalAccuracy.approximate,
            revisions=previous_revisions,
        )
        project.status = ProjectStatus.model_generating
        return await self._repo.save(project)

    async def run(self, project_id: str) -> None:
        """バックグラウンドで実行する本体。例外を外へ投げない.

        呼び出し元はレスポンスを返した後なので、ここで失敗しても
        HTTP エラーにはできない。失敗はプロジェクトに記録して伝える。
        """
        try:
            project = await self._repo.get(project_id)
        except Exception:
            logger.exception("3Dモデル生成: プロジェクトを取得できません id=%s", project_id)
            return

        try:
            await self._generate(project)
        except Mesh3DError as exc:
            await self._fail(project, str(exc))
        except meshproc.MeshProcessingError as exc:
            await self._fail(project, f"メッシュを処理できませんでした: {exc}")
        except Exception as exc:
            logger.exception("3Dモデル生成で予期しない失敗 id=%s", project_id)
            await self._fail(project, f"予期しないエラー: {exc}")

    async def _generate(self, project: Project) -> None:
        assert project.model is not None
        assert project.proposal is not None

        source_image = self._pick_source_image(project)

        project.model.job_status = JobStatus.running
        await self._repo.save(project)

        job_id = await self._provider.submit(
            GenerationRequest(image_url=source_image, with_texture=False)
        )
        project.model.job_id = job_id
        await self._repo.save(project)

        await self._await_completion(job_id)
        artifact = await self._provider.fetch(job_id)

        target = project.proposal.size_mm
        processed = meshproc.process(
            artifact,
            target_size_mm=(target.width, target.depth, target.height),
        )
        report = processed.report

        # 印刷用と表示用を別々に保存する。スライサは STL を、
        # アプリの3Dビューアは GLB を必要とするため。
        url = await self._storage.put(
            project_id=project.id, data=processed.stl, media_type="model/stl"
        )
        preview_url = await self._storage.put(
            project_id=project.id, data=processed.glb, media_type="model/gltf-binary"
        )

        project.model.url = url
        project.model.preview_url = preview_url
        project.model.format = "stl"
        project.model.watertight = report.watertight
        project.model.printable = report.printable
        project.model.face_count = report.face_count
        project.model.size_mm = Dimensions(
            width=report.size_mm[0], depth=report.size_mm[1], height=report.size_mm[2]
        )
        project.model.volume_mm3 = report.volume_mm3
        project.model.repair_actions = report.repair_actions
        project.model.warnings = list(report.warnings)

        if project.route is DesignRoute.mechanism:
            # 機構ルートは寸法が要件そのものなので、暫定であることを必ず伝える。
            project.model.warnings.append(
                "このモデルは画像から起こした暫定形状です。"
                "寸法が要件になっている物のため、寸法保証のある作り直し(機構ルート)が必要です。"
            )

        project.model.job_status = JobStatus.done
        project.status = ProjectStatus.model_review
        await self._repo.save(project)

    def _pick_source_image(self, project: Project) -> str:
        """外観画像を優先する。3D 化の入力として最も素直なため."""
        for image in project.images:
            if image.kind.value == "exterior":
                return image.url
        return project.images[0].url

    async def _await_completion(self, job_id: str) -> None:
        waited = 0.0
        while True:
            state = await self._provider.poll(job_id)
            if state == "done":
                return
            if state == "error":
                raise Mesh3DError("3Dモデルの生成に失敗しました")
            if waited >= self._poll_timeout:
                raise Mesh3DError(
                    f"3Dモデルの生成が {int(self._poll_timeout / 60)} 分以内に完了しませんでした"
                )
            await asyncio.sleep(self._poll_interval)
            waited += self._poll_interval

    async def _fail(self, project: Project, message: str) -> None:
        try:
            fresh = await self._repo.get(project.id)
            if fresh.model is None:
                fresh.model = Model3D()
            fresh.model.job_status = JobStatus.error
            fresh.model.error = message
            # 画像確認まで戻す。ユーザーが再試行できる状態にするため。
            fresh.status = ProjectStatus.image_review
            await self._repo.save(fresh)
        except Exception:
            logger.exception("3Dモデル生成の失敗を記録できません id=%s", project.id)
