"""アプリケーション設定.

環境変数(接頭辞 ``APP_``)または ``.env`` から読み込む。
値の一覧と意味は ``.env.example`` を参照。
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    local = "local"
    staging = "staging"
    production = "production"


class AuthMode(StrEnum):
    """認証の検証方式."""

    firebase = "firebase"
    """Firebase の ID トークンを検証する。本番はこれ。"""

    insecure_dev = "insecure_dev"
    """トークンを検証せず uid として扱う。Firebase 未設定でも開発できるようにするための
    ローカル専用モード。``environment`` が local 以外なら起動時に弾く。"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    environment: Environment = Environment.local
    version: str = "0.1.0"

    auth_mode: AuthMode = AuthMode.firebase
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    """サービスアカウント JSON のパス。未設定なら Application Default Credentials を使う
    (Cloud Run 上ではこちらが通常)。"""

    cors_origins: list[str] = Field(default_factory=list)
    """JSON 配列で指定する。例: APP_CORS_ORIGINS='["http://localhost:8080"]'"""

    @model_validator(mode="after")
    def _forbid_insecure_auth_outside_local(self) -> Settings:
        # 開発用の素通し認証が本番に紛れ込むと全ユーザーになりすませてしまうため、
        # 起動そのものを失敗させる。実行時チェックではなく設定段階で落とすのが要点。
        if self.auth_mode is AuthMode.insecure_dev and self.environment is not Environment.local:
            raise ValueError(
                f"auth_mode=insecure_dev は environment=local でのみ許可されます "
                f"(現在: environment={self.environment.value})"
            )
        return self

    @property
    def firebase_configured(self) -> bool:
        return self.auth_mode is AuthMode.firebase


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
