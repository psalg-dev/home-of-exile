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
    poe_ninja_league: str = "Keepers"

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

    # ---------------------------------------------------------------------------
    # LLM (M7) settings
    # ---------------------------------------------------------------------------

    # OpenAI API key — required for LLM explanations.
    # If empty, all requests fall back to template explanations.
    openai_api_key: str = ""

    # Model to use for explanations (cost-efficient default).
    llm_model: str = "gpt-4o-mini"

    # Per-call timeout in seconds before falling back to template.
    llm_timeout_seconds: float = 3.0

    # Daily USD spend cap. When reached, all requests fall back to templates.
    # Set to 0 to disable the cap.
    llm_daily_spend_cap_usd: float = 5.0

    # A/B test fraction receiving LLM explanations (0.0 = all template,
    # 1.0 = all LLM). 0.5 = 50/50 split.
    llm_ab_fraction: float = 0.5

    # Feature flag — master on/off switch for LLM explanations.
    llm_enabled: bool = True

    def allowed_origins_list(self) -> list[str]:
        """Parse allowed_origins into a list of origin strings.

        Returns:
            List of origin strings (stripped of whitespace).
        """
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Singleton settings instance
settings = Settings()
