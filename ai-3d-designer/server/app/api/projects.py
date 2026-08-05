"""STEP1〜3 のエンドポイント."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.deps import get_design_service
from app.domain.models import Idea, Project
from app.providers.imagegen import ImageGenerationError
from app.providers.llm import LLMError
from app.repositories.base import ProjectNotFoundError
from app.services.design import DesignService, InvalidStateError

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    image_urls: list[str] = Field(default_factory=list, max_length=8)


class RevisionRequest(BaseModel):
    request: str = Field(min_length=1, max_length=1000)


async def _load_owned(service: DesignService, project_id: str, user: AuthenticatedUser) -> Project:
    """所有者以外には存在自体を知らせない(403 ではなく 404 を返す)."""
    try:
        project = await service.get(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません") from exc

    if project.owner_uid != user.uid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません")
    return project


def _to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidStateError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, LLMError | ImageGenerationError):
        # 上流の生成 API 側の問題なので 502。クライアントは再試行してよい。
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    raise exc


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    """STEP1: アイデアを登録する."""
    return await service.create_project(
        owner_uid=user.uid,
        idea=Idea(text=body.text, image_urls=body.image_urls),
    )


@router.get("", response_model=list[Project])
async def list_projects(
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> list[Project]:
    return await service.list_for_owner(user.uid)


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    return await _load_owned(service, project_id, user)


@router.post("/{project_id}/proposal", response_model=Project)
async def generate_proposal(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    """STEP2: 企画を生成する."""
    project = await _load_owned(service, project_id, user)
    try:
        return await service.generate_proposal(project)
    except (InvalidStateError, LLMError) as exc:
        raise _to_http(exc) from exc


@router.post("/{project_id}/proposal/revise", response_model=Project)
async def revise_proposal(
    project_id: str,
    body: RevisionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    """STEP2: 修正指示を反映する."""
    project = await _load_owned(service, project_id, user)
    try:
        return await service.revise_proposal(project, body.request)
    except (InvalidStateError, LLMError) as exc:
        raise _to_http(exc) from exc


@router.post("/{project_id}/images", response_model=Project)
async def generate_images(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    """STEP3: 企画を承認して画像を生成する."""
    project = await _load_owned(service, project_id, user)
    try:
        return await service.generate_images(project)
    except (InvalidStateError, ImageGenerationError) as exc:
        raise _to_http(exc) from exc


@router.post("/{project_id}/images/revise", response_model=Project)
async def revise_images(
    project_id: str,
    body: RevisionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> Project:
    """STEP3: 修正指示を反映して画像を作り直す."""
    project = await _load_owned(service, project_id, user)
    try:
        return await service.revise_images(project, body.request)
    except (InvalidStateError, ImageGenerationError) as exc:
        raise _to_http(exc) from exc
