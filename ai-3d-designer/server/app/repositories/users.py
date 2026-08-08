"""ユーザー設定の永続化.

現状 AMS の装填状態だけを持つ。DESIGN.md §4-1 の users/{uid} に対応。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.domain.ams import AmsState


class UserSettings(BaseModel):
    uid: str
    ams: AmsState = Field(default_factory=AmsState)
    printer_model: str = "P2S"


class UserSettingsRepository(Protocol):
    async def get(self, uid: str) -> UserSettings:
        """未登録なら既定値を返す(存在しないことをエラーにしない)."""
        ...

    async def save(self, settings: UserSettings) -> UserSettings: ...


class InMemoryUserSettingsRepository:
    def __init__(self) -> None:
        self._items: dict[str, UserSettings] = {}
        self._lock = asyncio.Lock()

    async def get(self, uid: str) -> UserSettings:
        async with self._lock:
            stored = self._items.get(uid)
        return stored.model_copy(deep=True) if stored else UserSettings(uid=uid)

    async def save(self, settings: UserSettings) -> UserSettings:
        async with self._lock:
            self._items[settings.uid] = settings.model_copy(deep=True)
        return settings


_COLLECTION = "users"


class FirestoreUserSettingsRepository:
    def __init__(self, project_id: str | None = None) -> None:
        from google.cloud import firestore

        self._client = firestore.AsyncClient(project=project_id)

    def _doc(self, uid: str) -> Any:
        return self._client.collection(_COLLECTION).document(uid)

    async def get(self, uid: str) -> UserSettings:
        snapshot = await self._doc(uid).get()
        if not snapshot.exists:
            return UserSettings(uid=uid)
        return UserSettings.model_validate({**(snapshot.to_dict() or {}), "uid": uid})

    async def save(self, settings: UserSettings) -> UserSettings:
        payload = settings.model_dump(mode="json")
        payload.pop("uid", None)
        await self._doc(settings.uid).set(payload)
        return settings
