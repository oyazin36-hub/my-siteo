"""インメモリ実装。ローカル開発とテスト用.

プロセスを落とすと消える。Firebase 未作成でも Phase 1 の流れを通せるようにするためのもの。
"""

from __future__ import annotations

import asyncio

from app.domain.models import Project
from app.repositories.base import ProjectNotFoundError


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self._items: dict[str, Project] = {}
        self._lock = asyncio.Lock()

    async def create(self, project: Project) -> Project:
        async with self._lock:
            # コピーを保持する。呼び出し側が後で手元のオブジェクトを書き換えても
            # 保存済みの内容が黙って変わらないようにするため。
            self._items[project.id] = project.model_copy(deep=True)
        return project

    async def get(self, project_id: str) -> Project:
        async with self._lock:
            stored = self._items.get(project_id)
        if stored is None:
            raise ProjectNotFoundError(project_id)
        return stored.model_copy(deep=True)

    async def save(self, project: Project) -> Project:
        async with self._lock:
            if project.id not in self._items:
                raise ProjectNotFoundError(project.id)
            project.touch()
            self._items[project.id] = project.model_copy(deep=True)
        return project

    async def list_for_owner(self, owner_uid: str, limit: int = 50) -> list[Project]:
        async with self._lock:
            owned = [p for p in self._items.values() if p.owner_uid == owner_uid]
        owned.sort(key=lambda p: p.updated_at, reverse=True)
        return [p.model_copy(deep=True) for p in owned[:limit]]
