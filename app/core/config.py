from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "gift-tax-rag-server"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    openai_api_key: str
    openai_chat_model: str = "gpt-5-nano"
    openai_embedding_model: str = "text-embedding-3-small"

    chroma_path: str = "storage/chroma"
    chroma_collection_name: str = "gift_tax_documents"

    rag_top_k: int = 5
    rag_min_distance: float = 1.2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()