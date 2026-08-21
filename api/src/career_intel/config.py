"""Application settings, loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> career_intel -> src -> api
API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # The env file is anchored to the package, not to the working directory.
    # A relative "env_file" is resolved against the process CWD, which makes
    # configuration depend on where uvicorn was launched from: the repo root
    # holds a .env written for compose interpolation, api/ holds the one meant
    # for a local venv, and anywhere else holds none -- in which case every
    # field below silently falls back to its default and the misconfiguration
    # surfaces much later, far from its cause.
    #
    # In the container this path does not exist and pydantic skips it, leaving
    # the compose-provided environment in sole charge, which is what compose
    # already intends.
    #
    # extra="ignore" is deliberate, not laziness: the root .env carries
    # POSTGRES_* keys that only compose consumes, and "forbid" would reject
    # them outright if that file were ever read from here.
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/career_intel"

    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    max_upload_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
