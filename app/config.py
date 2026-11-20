"""Configuration management for SitePulse AI using pydantic-settings and python-dotenv."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = int(os.environ.get("PORT", "4000"))
    ENVIRONMENT: str = "development"
    APP_NAME: str = "SitePulse AI"
    APP_VERSION: str = "1.0.0"

    # Gemini AI configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Website extraction limits and controls
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    MAX_CONTENT_LENGTH: int = 5_242_880  # 5 MB
    MAX_REDIRECTS: int = 5
    MAX_SUBPAGES_TO_CRAWL: int = 2
    MAX_EXTRACTED_CHARS: int = 25_000

    # In-memory TTL cache for analysis results (prevents duplicate LLM and scraping calls)
    CACHE_TTL_SECONDS: int = 3600

    # Optional external search providers for verified competitor research
    TAVILY_API_KEY: Optional[str] = None
    SEARCH_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global settings singleton
settings = Settings()
