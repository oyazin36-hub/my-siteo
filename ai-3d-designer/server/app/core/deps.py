"""依存の組み立て.

設定に応じて実装を選ぶ場所をここ1箇所に閉じ込める。
サービスやAPI層は具体的な実装を知らない。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.core.config import AIMode, RepositoryMode, Settings, StorageMode
from app.providers.imagegen import ImageProvider, OpenAIImageProvider, StubImageProvider
from app.providers.llm import LLMProvider, OpenAILLMProvider, StubLLMProvider
from app.providers.storage import CloudImageStorage, ImageStorage, LocalImageStorage
from app.repositories.base import ProjectRepository
from app.repositories.memory import InMemoryProjectRepository
from app.services.design import DesignService


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


def build_storage(settings: Settings) -> ImageStorage:
    if settings.storage_mode is StorageMode.local:
        return LocalImageStorage(Path(settings.local_media_root))
    assert settings.firebase_storage_bucket is not None
    return CloudImageStorage(settings.firebase_storage_bucket)


def build_design_service(settings: Settings) -> DesignService:
    return DesignService(
        repository=build_repository(settings),
        llm=build_llm(settings),
        image_provider=build_image_provider(settings),
        storage=build_storage(settings),
    )


def get_design_service(request: Request) -> DesignService:
    service: DesignService | None = getattr(request.app.state, "design_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="サービスが初期化されていません",
        )
    return service


DesignServiceDep = Depends(get_design_service)
