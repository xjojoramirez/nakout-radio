from functools import lru_cache
from pathlib import Path
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
    track_gap_seconds: float = 2.0
    preload_lead_seconds: float = 20.0
    cookie_secure: bool = True
    loudness_target_db: float = -9.0
    loudness_max_boost_db: float = 6.0
    loudness_lookup_enabled: bool = True
    enrichment_enabled: bool = True
    enrichment_pause_seconds: float = 0.5
    enrichment_max_consecutive_errors: int = 5
    rotation_repeat_percent: int = 10
    rotation_min_window: int = 5
    rotation_fallback_window: int = 20
    changelog_path: str = str(
        Path(__file__).resolve().parents[2] / "docs" / "studio" / "changelog.md"
    )

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

    @field_validator("track_gap_seconds")
    @classmethod
    def _valid_gap(cls, v: float) -> float:
        if not 0 <= v <= 30:
            raise ValueError("track_gap_seconds must be between 0 and 30")
        return v

    @field_validator("preload_lead_seconds")
    @classmethod
    def _valid_preload_lead(cls, v: float) -> float:
        if not 0 <= v <= 300:
            raise ValueError("preload_lead_seconds must be between 0 and 300")
        return v

    @field_validator("loudness_target_db")
    @classmethod
    def _valid_loudness_target(cls, v: float) -> float:
        if not -60 <= v <= 0:
            raise ValueError("loudness_target_db must be between -60 and 0")
        return v

    @field_validator("loudness_max_boost_db")
    @classmethod
    def _valid_loudness_boost(cls, v: float) -> float:
        if not 0 <= v <= 24:
            raise ValueError("loudness_max_boost_db must be between 0 and 24")
        return v

    @field_validator("enrichment_pause_seconds")
    @classmethod
    def _valid_enrichment_pause(cls, v: float) -> float:
        if not 0 <= v <= 10:
            raise ValueError("enrichment_pause_seconds must be between 0 and 10")
        return v

    @field_validator("enrichment_max_consecutive_errors")
    @classmethod
    def _valid_enrichment_errors(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError(
                "enrichment_max_consecutive_errors must be between 1 and 50"
            )
        return v

    @field_validator("rotation_repeat_percent")
    @classmethod
    def _valid_rotation_percent(cls, v: int) -> int:
        if not 0 <= v <= 50:
            raise ValueError("rotation_repeat_percent must be between 0 and 50")
        return v

    @field_validator("rotation_min_window", "rotation_fallback_window")
    @classmethod
    def _valid_rotation_window(cls, v: int) -> int:
        if not 1 <= v <= 500:
            raise ValueError("rotation window sizes must be between 1 and 500")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
