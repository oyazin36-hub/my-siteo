"""プロジェクトの永続化の抽象."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import Project


class ProjectNotFoundError(Exception):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"プロジェクトが見つかりません: {project_id}")
        self.project_id = project_id


class ProjectRepository(Protocol):
    async def create(self, project: Project) -> Project: ...

    async def get(self, project_id: str) -> Project:
        """見つからなければ ProjectNotFoundError."""
        ...

    async def save(self, project: Project) -> Project: ...

    async def list_for_owner(self, owner_uid: str, limit: int = 50) -> list[Project]: ...
