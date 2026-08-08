"""ユーザー設定のエンドポイント(AMS の装填状態)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.deps import get_user_repository
from app.domain.ams import AMS_SLOT_COUNT, AmsState, LoadedSlot
from app.domain.filaments import CATALOG, Filament, by_product
from app.repositories.users import UserSettings, UserSettingsRepository

router = APIRouter(prefix="/me", tags=["settings"])


class UpdateAmsRequest(BaseModel):
    connected: bool = True
    slots: list[LoadedSlot] = Field(default_factory=list, max_length=AMS_SLOT_COUNT)


@router.get("/settings", response_model=UserSettings)
async def get_settings(
    user: AuthenticatedUser = Depends(get_current_user),
    repo: UserSettingsRepository = Depends(get_user_repository),
) -> UserSettings:
    return await repo.get(user.uid)


@router.put("/ams", response_model=UserSettings)
async def update_ams(
    body: UpdateAmsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: UserSettingsRepository = Depends(get_user_repository),
) -> UserSettings:
    """AMS に今なにが装填されているかを登録する.

    これが分かると「入れ替えが要るか」まで判断できるようになる。
    """
    seen: set[int] = set()
    for slot in body.slots:
        if slot.slot in seen:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"スロット {slot.slot} が重複しています"
            )
        seen.add(slot.slot)

        filament = by_product(slot.product)
        if filament is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"カタログにないフィラメントです: {slot.product}",
            )
        if not filament.has_color(slot.color):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{slot.product} に {slot.color} の取り扱いがありません",
            )
        if not filament.ams_compatible:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{slot.product} は AMS を通せません(外部スプールから給送してください)",
            )

    settings = await repo.get(user.uid)
    settings.ams = AmsState(connected=body.connected, slots=body.slots)
    return await repo.save(settings)


@router.get("/filaments", response_model=list[Filament])
async def list_filaments(
    _: AuthenticatedUser = Depends(get_current_user),
) -> list[Filament]:
    """選択肢を出すためのカタログ。AMS 登録画面で使う."""
    return CATALOG
