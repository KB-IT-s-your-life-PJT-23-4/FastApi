from functools import lru_cache

import chromadb
import pymysql
from openai import OpenAI
from pymysql.cursors import DictCursor

from app.core.config import get_settings
from app.repositories.interpretation_repository import (
    InterpretationRepository,
)
from app.repositories.law_repository import LawRepository
from app.repositories.tax_rule_repository import TaxRuleRepository
from app.services.answer_service import AnswerService
from app.services.chat_service import ChatService
from app.services.clarification_service import ClarificationService
from app.services.context_service import ContextService
from app.services.intent_service import IntentService
from app.services.retrieval_service import RetrievalService
from app.services.tax_rule_service import TaxRuleService


@lru_cache
def get_openai_client() -> OpenAI:
    settings = get_settings()

    return OpenAI(
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_openai_embedding_client() -> OpenAI:
    settings = get_settings()

    return OpenAI(
        api_key=settings.openai_embedding_api_key,
    )


@lru_cache
def get_chroma_client():
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_path)


@lru_cache
def get_interpretation_repository() -> InterpretationRepository:
    settings = get_settings()
    collection = get_chroma_client().get_collection(
        settings.interpretation_collection_name
    )
    return InterpretationRepository(
        collection=collection,
        embedding_client=get_openai_embedding_client(),
        embedding_model=settings.openai_embedding_model,
    )


@lru_cache
def get_law_repository() -> LawRepository:
    settings = get_settings()
    collection = get_chroma_client().get_collection(
        settings.law_collection_name
    )
    return LawRepository(
        collection=collection,
        embedding_client=get_openai_embedding_client(),
        embedding_model=settings.openai_embedding_model,
    )


def create_mirizoom_db_connection():
    settings = get_settings()
    return pymysql.connect(
        host=settings.mirizoom_db_host,
        port=settings.mirizoom_db_port,
        user=settings.mirizoom_db_user,
        password=settings.mirizoom_db_password,
        database=settings.mirizoom_db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=settings.mirizoom_db_connect_timeout,
        autocommit=True,
    )


@lru_cache
def get_tax_rule_repository() -> TaxRuleRepository:
    return TaxRuleRepository(
        connection_factory=create_mirizoom_db_connection
    )


@lru_cache
def get_tax_rule_service() -> TaxRuleService:
    return TaxRuleService(get_tax_rule_repository())


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    client = get_openai_client()

    return ChatService(
        intent_service=IntentService(
            client=client,
            model=settings.openai_chat_model,
        ),
        retrieval_service=RetrievalService(
            interpretation_repository=(
                get_interpretation_repository()
            ),
            law_repository=get_law_repository(),
            interpretation_top_k=settings.interpretation_top_k,
            law_top_k=settings.law_top_k,
            law_chunk_top_k=settings.law_chunk_top_k,
        ),
        clarification_service=ClarificationService(
            client=client,
            model=settings.openai_chat_model,
        ),
        answer_service=AnswerService(
            client=client,
            model=settings.openai_chat_model,
        ),
        context_service=ContextService(
            tax_rule_service=get_tax_rule_service(),
        ),
    )
