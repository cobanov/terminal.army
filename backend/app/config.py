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

    # --- Server sharding -----------------------------------------------------
    # Each backend instance represents one server (= one universe / shard).
    # The lobby (sakusen.space) lists all known servers from LOBBY_SERVERS.
    # Server identifier (s1, s2, s3, ...). Each shard is reachable at
    # <id>.sakusen.space.
    server_name: str = "s1"
    server_description: str = "the first universe"
    server_max_users: int = 5000
    # When true, this instance behaves as the lobby (sakusen.space root): the
    # / route shows the server picker instead of forwarding to local signup,
    # and signup/login are disabled locally (users get sent to a shard).
    is_lobby: bool = False
    # Comma-separated list of shard servers, used only when IS_LOBBY=true.
    # Format: "id=url[:status][,id2=url2[:status]]" where status is one of
    # live (default) or coming-soon.
    # Example: "s1=https://s1.sakusen.space,s2=https://s2.sakusen.space:coming-soon"
    lobby_servers: str = ""
    # If set, the dashboard topbar shows a "← back to lobby" link pointing
    # here. Empty = this instance acts as its own lobby.
    lobby_url: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
