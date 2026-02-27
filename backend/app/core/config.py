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

    # Database (PostgreSQL)
    database_url: str = "postgresql://hoe:hoe@localhost:5432/hoe"

    # poe.ninja
    poe_ninja_league: str = "Settlers"

    # RePoE data directory (relative to the backend/ directory)
    repoe_data_dir: str = "../data/repoe"

    # LuaJIT pool
    luajit_pool_size: int = 2
    # Path to the PoB src/ directory containing HeadlessWrapper.lua
    pob_src_dir: str = "/pob/src"
    # LuaJIT binary command
    luajit_cmd: str = "luajit"

    # CORS — comma-separated list of allowed origins.
    # Defaults to the Vite dev server; override in production.
    allowed_origins: str = "http://localhost:5173"

    # Rate limiting — max analysis requests per IP per hour (0 = disabled)
    rate_limit_per_hour: int = 10

    # Environment label
    environment: str = "development"

    def allowed_origins_list(self) -> list[str]:
        """Parse allowed_origins into a list of origin strings.

        Returns:
            List of origin strings (stripped of whitespace).
        """
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Singleton settings instance
settings = Settings()
