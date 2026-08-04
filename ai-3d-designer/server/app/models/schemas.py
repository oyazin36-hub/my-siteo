"""API のリクエスト/レスポンススキーマ."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str
    environment: str
    auth_mode: str
    """クライアントが「今どちらの認証方式に繋いでいるか」を確認できるようにする。
    ローカル開発で Firebase に繋いだつもりが素通しモードだった、という取り違えを防ぐ。"""


class MeResponse(BaseModel):
    uid: str
    email: str | None = None
    is_anonymous: bool
