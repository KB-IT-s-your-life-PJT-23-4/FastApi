from functools import lru_cache

import chromadb
from openai import OpenAI

from app.core.config import get_settings
from app.repositories.interpretation_repository import (
    InterpretationRepository,
)
from app.repositories.law_repository import LawRepository
from app.services.answer_service import AnswerService
from app.services.chat_service import ChatService
from app.services.clarification_service import ClarificationService
from app.services.context_service import ContextService
from app.services.intent_service import IntentService
from app.services.retrieval_service import RetrievalService


@lru_cache
def get_openai_client() -> OpenAI:
    settings = get_settings()

    return OpenAI(
        api_key=settings.openai_api_key,
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
        embedding_client=get_openai_client(),
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
        embedding_client=get_openai_client(),
        embedding_model=settings.openai_embedding_model,
    )


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
        ),
        clarification_service=ClarificationService(
            client=client,
            model=settings.openai_chat_model,
        ),
        answer_service=AnswerService(
            client=client,
            model=settings.openai_chat_model,
        ),
        context_service= ContextService(),
    )
