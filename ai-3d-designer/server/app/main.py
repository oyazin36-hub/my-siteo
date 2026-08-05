"""AI 3D Product Designer — バックエンド.

Phase 0: 疎通確認と認証
Phase 1: STEP1〜3(アイデア入力・企画提案・画像生成)
Phase 2: STEP4(3Dモデル生成)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.projects import router as projects_router
from app.api.routes import router as system_router
from app.core.auth import build_token_verifier
from app.core.config import StorageMode, get_settings
from app.core.deps import build_services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 外部依存の生成は起動時に一度だけ。設定の誤りを起動時点で表面化させる狙いもある。
    settings = get_settings()
    app.state.token_verifier = build_token_verifier(settings)
    app.state.design_service, app.state.modeling_service = build_services(settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI 3D Product Designer API",
        version=settings.version,
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(system_router)
    app.include_router(projects_router)

    if settings.storage_mode is StorageMode.local:
        # 開発時に生成画像をアプリから表示できるようにする。
        media_root = Path(settings.local_media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=media_root), name="media")

    return app


app = create_app()
