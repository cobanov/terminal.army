from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./ogame.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    # Long-lived: 1 year. Key gibi davranir.
    jwt_expire_minutes: int = 60 * 24 * 365

    default_universe_name: str = "Galactica"
    default_universe_speed: int = 1

    scheduler_interval_seconds: int = 5

    cors_origins: str = "*"

    # Username of the operator who can change runtime universe settings
    # (speed, etc.) via /admin/* endpoints. Empty = no one is admin.
    admin_username: str = ""

    # Server identity. Shown in the topbar and /stats endpoint.
    server_name: str = "s1"
    server_description: str = "the first universe"
    server_max_users: int = 5000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
