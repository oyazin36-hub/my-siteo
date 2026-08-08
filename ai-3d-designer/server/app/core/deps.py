"""依存の組み立て.

設定に応じて実装を選ぶ場所をここ1箇所に閉じ込める。
サービスやAPI層は具体的な実装を知らない。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.core.config import (
    AIMode,
    CadMode,
    Mesh3DMode,
    RepositoryMode,
    Settings,
    SlicerMode,
    StorageMode,
)
from app.providers.cadgen import CadCodeProvider, ClaudeCadProvider, StubCadProvider
from app.providers.imagegen import ImageProvider, OpenAIImageProvider, StubImageProvider
from app.providers.llm import LLMProvider, OpenAILLMProvider, StubLLMProvider
from app.providers.mesh3d import Mesh3DProvider, StubMeshProvider, TripoMeshProvider
from app.providers.openscad import OpenScadRenderer
from app.providers.parts import ClaudePartsDecomposer, PartsDecomposer, StubPartsDecomposer
from app.providers.slicer import BambuStudioCliSlicer, HeuristicSlicer, Slicer
from app.providers.storage import BlobStorage, CloudBlobStorage, LocalBlobStorage
from app.repositories.base import ProjectRepository
from app.repositories.memory import InMemoryProjectRepository
from app.repositories.users import (
    InMemoryUserSettingsRepository,
    UserSettingsRepository,
)
from app.services.cad import CadService
from app.services.design import DesignService
from app.services.materials import MaterialsService
from app.services.modeling import ModelingService
from app.services.printing import PrintingService


def build_repository(settings: Settings) -> ProjectRepository:
    if settings.repository_mode is RepositoryMode.memory:
        return InMemoryProjectRepository()

    from app.repositories.firestore import FirestoreProjectRepository

    return FirestoreProjectRepository(settings.firebase_project_id)


def build_llm(settings: Settings) -> LLMProvider:
    if settings.ai_mode is AIMode.stub:
        return StubLLMProvider()
    # 設定バリデータでキーの存在は保証済み。
    assert settings.openai_api_key is not None
    return OpenAILLMProvider(settings.openai_api_key, settings.openai_llm_model)


def build_image_provider(settings: Settings) -> ImageProvider:
    if settings.ai_mode is AIMode.stub:
        return StubImageProvider()
    assert settings.openai_api_key is not None
    return OpenAIImageProvider(settings.openai_api_key, settings.openai_image_model)


def build_storage(settings: Settings) -> BlobStorage:
    if settings.storage_mode is StorageMode.local:
        return LocalBlobStorage(Path(settings.local_media_root))
    assert settings.firebase_storage_bucket is not None
    return CloudBlobStorage(settings.firebase_storage_bucket)


def build_mesh_provider(settings: Settings) -> Mesh3DProvider:
    if settings.mesh3d_mode is Mesh3DMode.stub:
        return StubMeshProvider()
    assert settings.tripo_api_key is not None
    return TripoMeshProvider(settings.tripo_api_key, settings.tripo_model_version)


def build_user_repository(settings: Settings) -> UserSettingsRepository:
    if settings.repository_mode is RepositoryMode.memory:
        return InMemoryUserSettingsRepository()

    from app.repositories.users import FirestoreUserSettingsRepository

    return FirestoreUserSettingsRepository(settings.firebase_project_id)


def build_parts_decomposer(settings: Settings) -> PartsDecomposer:
    if settings.cad_mode is CadMode.stub:
        return StubPartsDecomposer()
    assert settings.anthropic_api_key is not None
    return ClaudePartsDecomposer(settings.anthropic_api_key, settings.anthropic_cad_model)


def build_cad_code_provider(settings: Settings) -> CadCodeProvider:
    if settings.cad_mode is CadMode.stub:
        return StubCadProvider()
    assert settings.anthropic_api_key is not None
    return ClaudeCadProvider(settings.anthropic_api_key, settings.anthropic_cad_model)


def build_cad_service(settings: Settings) -> CadService:
    return CadService(
        code_provider=build_cad_code_provider(settings),
        renderer=OpenScadRenderer(settings.openscad_binary),
    )


def build_slicer(settings: Settings) -> Slicer:
    if settings.slicer_mode is SlicerMode.bambu_cli:
        return BambuStudioCliSlicer(settings.bambu_studio_binary)
    return HeuristicSlicer()


def build_services(
    settings: Settings,
) -> tuple[DesignService, ModelingService, PrintingService, UserSettingsRepository]:
    """リポジトリとストレージは 2 サービスで共有する.

    別々に作るとインメモリ実装のときに保存先が分かれ、片方の書き込みが
    もう片方から見えなくなる。
    """
    repository = build_repository(settings)
    storage = build_storage(settings)

    design = DesignService(
        repository=repository,
        llm=build_llm(settings),
        image_provider=build_image_provider(settings),
        storage=storage,
    )
    modeling = ModelingService(
        repository=repository,
        mesh_provider=build_mesh_provider(settings),
        storage=storage,
        gen_source=settings.mesh3d_mode.value,
        cad_service=build_cad_service(settings),
    )
    printing = PrintingService(
        repository=repository,
        storage=storage,
        slicer=build_slicer(settings),
        materials=MaterialsService(decomposer=build_parts_decomposer(settings)),
    )
    return design, modeling, printing, build_user_repository(settings)


def get_design_service(request: Request) -> DesignService:
    service: DesignService | None = getattr(request.app.state, "design_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="サービスが初期化されていません",
        )
    return service


def get_modeling_service(request: Request) -> ModelingService:
    service: ModelingService | None = getattr(request.app.state, "modeling_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="サービスが初期化されていません",
        )
    return service


def get_printing_service(request: Request) -> PrintingService:
    service: PrintingService | None = getattr(request.app.state, "printing_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="サービスが初期化されていません",
        )
    return service


def get_user_repository(request: Request) -> UserSettingsRepository:
    repo: UserSettingsRepository | None = getattr(request.app.state, "user_repository", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="サービスが初期化されていません",
        )
    return repo


DesignServiceDep = Depends(get_design_service)
