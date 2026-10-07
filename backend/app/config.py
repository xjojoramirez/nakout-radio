from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    yt_api_key: str = ""
    admin_password: str = ""
    secret_key: str = ""
    genre_tz: str = "Asia/Manila"
    database_url: str = "sqlite:///./radio.db"
    frontend_origin: str = "http://localhost:5173"
    cache_ttl_minutes: int = 60
    cookie_secure: bool = True

    @field_validator("yt_api_key", "admin_password", "secret_key")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required config value must not be empty")
        return v

    @field_validator("genre_tz")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as exc:
            raise ValueError(f"invalid timezone: {v}") from exc
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
