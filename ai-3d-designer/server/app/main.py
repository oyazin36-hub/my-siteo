"""AI 3D Product Designer — バックエンド.

Phase 0 の範囲: 疎通確認と認証のみ。
Phase 1 以降で projects ルーター(企画生成・画像生成)を追加する。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.auth import build_token_verifier
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 検証器の生成は起動時に一度だけ。Firebase の初期化コストをリクエスト毎に
    # 払わないためと、認証設定の誤りを起動時点で表面化させるため。
    settings = get_settings()
    app.state.token_verifier = build_token_verifier(settings)
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

    app.include_router(router)
    return app


app = create_app()
