"""Firestore 実装.

google-cloud-firestore は依存が重いので遅延 import する。
Firebase 未設定の環境ではこのモジュールを import しても副作用がない。
"""

from __future__ import annotations

from typing import Any

from app.domain.models import Project
from app.repositories.base import ProjectNotFoundError

_COLLECTION = "projects"


class FirestoreProjectRepository:
    def __init__(self, project_id: str | None = None) -> None:
        from google.cloud import firestore

        self._client = firestore.AsyncClient(project=project_id)

    def _doc(self, project_id: str) -> Any:
        return self._client.collection(_COLLECTION).document(project_id)

    async def create(self, project: Project) -> Project:
        await self._doc(project.id).set(_to_document(project))
        return project

    async def get(self, project_id: str) -> Project:
        snapshot = await self._doc(project_id).get()
        if not snapshot.exists:
            raise ProjectNotFoundError(project_id)
        return _from_document(project_id, snapshot.to_dict() or {})

    async def save(self, project: Project) -> Project:
        project.touch()
        # merge ではなく set。ドメイン側が常に全体を持っているので、
        # 部分更新による不整合を作らない。
        await self._doc(project.id).set(_to_document(project))
        return project

    async def list_for_owner(self, owner_uid: str, limit: int = 50) -> list[Project]:
        from google.cloud import firestore

        query = (
            self._client.collection(_COLLECTION)
            .where(filter=firestore.FieldFilter("owner_uid", "==", owner_uid))
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [_from_document(doc.id, doc.to_dict() or {}) async for doc in query.stream()]


def _to_document(project: Project) -> dict[str, Any]:
    # id はドキュメント ID として持つので本文からは外す。
    payload = project.model_dump(mode="json")
    payload.pop("id", None)
    return payload


def _from_document(project_id: str, data: dict[str, Any]) -> Project:
    return Project.model_validate({**data, "id": project_id})
