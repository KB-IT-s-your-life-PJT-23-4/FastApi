from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_name: str = "gift-tax-rag-server"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    openai_api_key: str
    openai_chat_model: str = "gpt-4o-mini"
    # openai_chat_model: str = "gpt-5-nano"

    openai_embedding_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    chroma_path: str = str(BASE_DIR / "storage" / "chroma")
    law_collection_name: str = "gift_tax_law_articles"
    interpretation_collection_name: str = "gift_tax_documents"

    interpretation_top_k: int = Field(default=4, ge=1, le=20)
    law_top_k: int = Field(default=2, ge=1, le=20)
    law_chunk_top_k: int = Field(default=10, ge=1, le=100)

    mirizoom_db_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("MIRIZOOM_DB_HOST", "DB_HOST"),
    )
    mirizoom_db_port: int = Field(
        default=3306,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("MIRIZOOM_DB_PORT", "DB_PORT"),
    )
    mirizoom_db_name: str = Field(
        default="miriZoom",
        validation_alias=AliasChoices("MIRIZOOM_DB_NAME", "DB_NAME"),
    )
    mirizoom_db_user: str = Field(
        default="root",
        validation_alias=AliasChoices("MIRIZOOM_DB_USER", "DB_USERNAME"),
    )
    mirizoom_db_password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "MIRIZOOM_DB_PASSWORD",
            "DB_PASSWORD",
        ),
    )
    mirizoom_db_connect_timeout: int = Field(
        default=5,
        ge=1,
        le=30,
        validation_alias=AliasChoices(
            "MIRIZOOM_DB_CONNECT_TIMEOUT",
            "DB_CONNECT_TIMEOUT",
        ),
    )

    model_config = SettingsConfigDict(
        # Process environment variables (for example Docker's --env-file)
        # take precedence. These files also support local and mounted setups.
        env_file=(".env", "app.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
