from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_name: str = "gift-tax-rag-server"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    openai_api_key: str
    openai_chat_model: str = "gpt-5-nano"
    openai_embedding_model: str = "text-embedding-3-small"

    chroma_path: str = str(BASE_DIR / "storage" / "chroma")
    law_collection_name: str = "gift_tax_laws"
    interpretation_collection_name: str = "nts_interpretations"

    interpretation_top_k: int = Field(default=4, ge=1, le=20)
    law_top_k = Field(default=2, ge=1, le=20)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()