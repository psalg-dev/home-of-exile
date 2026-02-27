"""Application settings loaded from environment variables via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    All values can be set via environment variables or a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://hoe:hoe@localhost:5432/hoe"

    # poe.ninja
    poe_ninja_league: str = "Settlers"

    # RePoE data directory (relative to the backend/ directory)
    repoe_data_dir: str = "../data/repoe"

    # LuaJIT pool size (used in later milestones)
    luajit_pool_size: int = 2


# Singleton settings instance
settings = Settings()
