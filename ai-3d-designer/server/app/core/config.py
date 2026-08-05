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


class AIMode(StrEnum):
    openai = "openai"
    stub = "stub"
    """API キーなしで開発するためのスタブ。実際の生成は行わない。"""


class Mesh3DMode(StrEnum):
    tripo = "tripo"
    stub = "stub"
    """企画の寸法どおりの箱を返すスタブ。実際の形状生成は行わない。"""


class RepositoryMode(StrEnum):
    firestore = "firestore"
    memory = "memory"
    """プロセス終了で消える。ローカル開発とテスト用。"""


class StorageMode(StrEnum):
    cloud = "cloud"
    local = "local"
    """ローカルのファイルシステムに保存し、/media で配信する。開発用。"""


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

    firebase_storage_bucket: str | None = None

    ai_mode: AIMode = AIMode.openai
    openai_api_key: str | None = None
    openai_llm_model: str = "gpt-4o-2024-08-06"
    openai_image_model: str = "gpt-image-1"

    mesh3d_mode: Mesh3DMode = Mesh3DMode.tripo
    tripo_api_key: str | None = None
    tripo_model_version: str | None = None
    """未指定なら SDK の既定版を使う。"""

    repository_mode: RepositoryMode = RepositoryMode.firestore
    storage_mode: StorageMode = StorageMode.cloud
    local_media_root: str = "./var/media"
    """storage_mode=local のときの保存先ディレクトリ。"""

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

    @model_validator(mode="after")
    def _forbid_stub_ai_outside_local(self) -> Settings:
        # スタブは実際には何も生成しない。本番で有効になると、生成できたように見えて
        # 中身が偽物という最悪の壊れ方をするため、起動時に落とす。
        if self.ai_mode is AIMode.stub and self.environment is not Environment.local:
            raise ValueError(
                f"ai_mode=stub は environment=local でのみ許可されます "
                f"(現在: environment={self.environment.value})"
            )
        return self

    @model_validator(mode="after")
    def _forbid_stub_mesh_outside_local(self) -> Settings:
        if self.mesh3d_mode is Mesh3DMode.stub and self.environment is not Environment.local:
            raise ValueError(
                f"mesh3d_mode=stub は environment=local でのみ許可されます "
                f"(現在: environment={self.environment.value})"
            )
        return self

    @model_validator(mode="after")
    def _require_tripo_key_when_used(self) -> Settings:
        if self.mesh3d_mode is Mesh3DMode.tripo and not self.tripo_api_key:
            raise ValueError(
                "mesh3d_mode=tripo には APP_TRIPO_API_KEY が必要です。"
                "キーがまだ無い場合は APP_MESH3D_MODE=stub を指定してください"
                "(environment=local のときのみ)"
            )
        return self

    @model_validator(mode="after")
    def _require_openai_key_when_used(self) -> Settings:
        if self.ai_mode is AIMode.openai and not self.openai_api_key:
            raise ValueError(
                "ai_mode=openai には APP_OPENAI_API_KEY が必要です。"
                "キーがまだ無い場合は APP_AI_MODE=stub を指定してください"
                "(environment=local のときのみ)"
            )
        return self

    @model_validator(mode="after")
    def _require_bucket_for_cloud_storage(self) -> Settings:
        if self.storage_mode is StorageMode.cloud and not self.firebase_storage_bucket:
            raise ValueError("storage_mode=cloud には APP_FIREBASE_STORAGE_BUCKET が必要です")
        return self

    @property
    def firebase_configured(self) -> bool:
        return self.auth_mode is AuthMode.firebase


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
