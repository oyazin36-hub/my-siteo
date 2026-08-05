"""STEP1〜3 のオーケストレーション.

状態機械の遷移はすべてここに集約する。API 層は認可と HTTP への変換だけを行う。
"""

from __future__ import annotations

import uuid

from app.domain.models import (
    GeneratedImage,
    Idea,
    ImageKind,
    Project,
    ProjectStatus,
    Proposal,
    Revision,
)
from app.providers.imagegen import ImageProvider
from app.providers.llm import LLMProvider, ProposalDraft
from app.providers.prompts import build_image_prompt, build_image_revision_prompt
from app.providers.storage import ImageStorage
from app.repositories.base import ProjectRepository

#: STEP3 で生成する画像の種類と順序。
DEFAULT_IMAGE_KINDS: tuple[ImageKind, ...] = (
    ImageKind.exterior,
    ImageKind.scene,
    ImageKind.exploded,
    ImageKind.internal,
    ImageKind.dimensions,
)


class InvalidStateError(Exception):
    """現在の状態では実行できない操作."""

    def __init__(self, current: ProjectStatus, action: str) -> None:
        super().__init__(f"状態 {current.value} では「{action}」を実行できません")
        self.current = current
        self.action = action


class DesignService:
    def __init__(
        self,
        *,
        repository: ProjectRepository,
        llm: LLMProvider,
        image_provider: ImageProvider,
        storage: ImageStorage,
    ) -> None:
        self._repo = repository
        self._llm = llm
        self._images = image_provider
        self._storage = storage

    # --- 参照 ---

    async def get(self, project_id: str) -> Project:
        """見つからなければ ProjectNotFoundError."""
        return await self._repo.get(project_id)

    async def list_for_owner(self, owner_uid: str) -> list[Project]:
        return await self._repo.list_for_owner(owner_uid)

    # --- STEP1 ---

    async def create_project(self, *, owner_uid: str, idea: Idea) -> Project:
        project = Project(
            id=uuid.uuid4().hex,
            owner_uid=owner_uid,
            idea=idea,
            status=ProjectStatus.idea_input,
        )
        return await self._repo.create(project)

    # --- STEP2 ---

    async def generate_proposal(self, project: Project) -> Project:
        if project.status not in (ProjectStatus.idea_input, ProjectStatus.proposing):
            raise InvalidStateError(project.status, "企画の生成")

        draft = await self._llm.draft_proposal(idea=project.idea)
        self._apply_draft(project, draft)
        project.status = ProjectStatus.proposal_review
        return await self._repo.save(project)

    async def revise_proposal(self, project: Project, request: str) -> Project:
        if project.status is not ProjectStatus.proposal_review or project.proposal is None:
            raise InvalidStateError(project.status, "企画の修正")

        previous_revisions = list(project.proposal.revisions)
        draft = await self._llm.draft_proposal(
            idea=project.idea,
            current=project.proposal,
            revision_request=request,
        )
        self._apply_draft(project, draft)

        # 修正履歴は企画が差し替わっても引き継ぐ。何をどう直してきたかが辿れなくなるため。
        assert project.proposal is not None
        project.proposal.revisions = [*previous_revisions, Revision(request=request)]
        return await self._repo.save(project)

    # --- STEP3 ---

    async def generate_images(
        self, project: Project, kinds: tuple[ImageKind, ...] = DEFAULT_IMAGE_KINDS
    ) -> Project:
        if project.status is not ProjectStatus.proposal_review or project.proposal is None:
            raise InvalidStateError(project.status, "画像の生成")

        project.status = ProjectStatus.image_generating
        await self._repo.save(project)

        project.images = await self._render(project, kinds, revision_request=None)
        project.status = ProjectStatus.image_review
        return await self._repo.save(project)

    async def revise_images(
        self,
        project: Project,
        request: str,
        kinds: tuple[ImageKind, ...] = DEFAULT_IMAGE_KINDS,
    ) -> Project:
        if project.status is not ProjectStatus.image_review or project.proposal is None:
            raise InvalidStateError(project.status, "画像の修正")

        project.status = ProjectStatus.image_generating
        await self._repo.save(project)

        project.images = await self._render(project, kinds, revision_request=request)
        project.image_revisions.append(Revision(request=request))
        project.status = ProjectStatus.image_review
        return await self._repo.save(project)

    # --- 内部 ---

    def _apply_draft(self, project: Project, draft: ProposalDraft) -> None:
        project.route = draft.route
        project.title = draft.product_name
        project.proposal = Proposal(
            product_name=draft.product_name,
            concept=draft.concept,
            size_mm=draft.size_mm,
            capacity=draft.capacity,
            mechanism=draft.mechanism,
            material=draft.material,
            print_time_est_min=draft.print_time_est_min,
            features=draft.features,
        )

    async def _render(
        self,
        project: Project,
        kinds: tuple[ImageKind, ...],
        *,
        revision_request: str | None,
    ) -> list[GeneratedImage]:
        proposal = project.proposal
        assert proposal is not None

        rendered: list[GeneratedImage] = []
        for kind in kinds:
            prompt = (
                build_image_prompt(proposal, kind.value)
                if revision_request is None
                else build_image_revision_prompt(proposal, kind.value, revision_request)
            )
            generated = await self._images.generate(prompt)
            url = await self._storage.put(
                project_id=project.id,
                data=generated.data,
                media_type=generated.media_type,
            )
            rendered.append(GeneratedImage(kind=kind, url=url, prompt=prompt))
        return rendered
