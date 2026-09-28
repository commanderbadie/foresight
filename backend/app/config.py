from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # SQLite works out of the box; use PostgreSQL for the real deployment:
    # postgresql+psycopg://foresight:foresight@localhost:5432/foresight
    database_url: str = f"sqlite:///{BACKEND_DIR / 'foresight.db'}"

    jwt_secret: str = "change-me-in-.env-this-is-only-for-local-development"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ML model: trained TAWOS model if present, else the synthetic demo model.
    model_path: Path = BACKEND_DIR / "models" / "tawos" / "model.joblib"
    demo_model_path: Path = BACKEND_DIR / "models" / "demo" / "model.joblib"

    # Local LLM through Ollama (free, runs on your machine). Leave as is to use
    # the rule-based offline assistant when Ollama is not running.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    llm_timeout_seconds: float = 60.0

    @field_validator("model_path", "demo_model_path")
    @classmethod
    def _resolve(cls, v: Path) -> Path:
        v = Path(v)
        return v if v.is_absolute() else BACKEND_DIR / v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
