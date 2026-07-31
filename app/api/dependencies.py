from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings
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
def get_chat_service() -> ChatService:
    settings = get_settings()
    client = get_openai_client()

    return ChatService(
        intent_service=IntentService(
            client=client,
            model=settings.openai_chat_model,
        ),
        retrieval_service=RetrievalService(
            interpretation_repository=...,
            law_repository=...,
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