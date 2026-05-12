from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Constants for production safety checks.
DEV_JWT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # `env=dev` allows defaults like wildcard CORS and the placeholder JWT
    # secret. `env=prod` rejects them at startup.
    env: str = "dev"

    database_url: str = "sqlite+aiosqlite:///./tarmy.db"
    jwt_secret: str = DEV_JWT_SECRET
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

    def assert_production_safe(self) -> None:
        """Fail loudly in production if any insecure default is still in use."""
        if self.env != "prod":
            return
        problems: list[str] = []
        if self.jwt_secret == DEV_JWT_SECRET:
            problems.append("JWT_SECRET is the dev default — generate with `openssl rand -hex 32`")
        if self.cors_origins.strip() == "*":
            problems.append(
                "CORS_ORIGINS=* is unsafe in prod with credentialed cookies — set explicit origin(s)"
            )
        if not self.admin_username.strip():
            problems.append("ADMIN_USERNAME unset — set the operator username")
        if problems:
            joined = "\n  - ".join(problems)
            raise RuntimeError(
                f"Refusing to start in ENV=prod with insecure defaults:\n  - {joined}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
