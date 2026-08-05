"""STEP1〜3 のエンドポイント."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.deps import get_design_service, get_modeling_service, get_printing_service
from app.domain.models import Idea, Project
from app.providers.imagegen import ImageGenerationError
from app.providers.llm import LLMError
from app.repositories.base import ProjectNotFoundError
from app.services.design import DesignService, InvalidStateError
from app.services.modeling import ModelingService
from app.services.printing import PrintingService
from app.services.threemf import ThreeMfError

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


# --- STEP4: 3Dモデル ---


@router.post(
    "/{project_id}/model",
    response_model=Project,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_model(
    project_id: str,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
    modeling: ModelingService = Depends(get_modeling_service),
) -> Project:
    """STEP4: 画像を承認して3Dモデルの生成を開始する.

    生成には数分かかるため受け付けだけ行い 202 を返す。
    進行状況はプロジェクトを取得して model.job_status を見る。
    """
    project = await _load_owned(service, project_id, user)
    try:
        queued = await modeling.enqueue(project)
    except InvalidStateError as exc:
        raise _to_http(exc) from exc

    background.add_task(modeling.run, project_id)
    return queued


@router.post(
    "/{project_id}/model/revise",
    response_model=Project,
    status_code=status.HTTP_202_ACCEPTED,
)
async def revise_model(
    project_id: str,
    body: RevisionRequest,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
    modeling: ModelingService = Depends(get_modeling_service),
) -> Project:
    """STEP4: 3Dモデルを作り直す."""
    project = await _load_owned(service, project_id, user)
    try:
        queued = await modeling.enqueue(project, revision_request=body.request)
    except InvalidStateError as exc:
        raise _to_http(exc) from exc

    background.add_task(modeling.run, project_id)
    return queued


# --- STEP5-6: 印刷データ ---


@router.post("/{project_id}/print", response_model=Project)
async def build_print_data(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
    printing: PrintingService = Depends(get_printing_service),
) -> Project:
    """STEP5-6: 3Dモデルを承認して、Bambu Studio で開ける 3MF を作る."""
    project = await _load_owned(service, project_id, user)
    try:
        return await printing.build(project)
    except InvalidStateError as exc:
        raise _to_http(exc) from exc
    except ThreeMfError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc


# --- 添付画像のアップロード ---

#: 受け付ける画像形式と 1 枚あたりの上限。
_ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadedImage(BaseModel):
    url: str


@router.post("/uploads", response_model=UploadedImage, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: DesignService = Depends(get_design_service),
) -> UploadedImage:
    """参考画像をアップロードして URL を得る.

    ここで得た URL を POST /projects の image_urls に渡す。
    """
    if file.content_type not in _ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"対応していない形式です: {file.content_type or '不明'}"
            "(PNG か JPEG を指定してください)",
        )

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"画像が大きすぎます({len(data) // 1024 // 1024}MB)。10MB 以下にしてください",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "空のファイルです")

    # プロジェクト作成前なのでユーザー単位の領域に置く。
    url = await service.store_upload(owner_uid=user.uid, data=data, media_type=file.content_type)
    return UploadedImage(url=url)
