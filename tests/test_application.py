from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.constants import RAG_INTENTS
from app.main import app
from app.repositories.interpretation_repository import (
    InterpretationRepository,
)
from app.services.context_service import ContextService
from app.services.retrieval_service import RetrievalService


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_chat_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/clarification" in paths


def test_all_gift_intents_use_rag() -> None:
    assert "product" in RAG_INTENTS
    assert "other_gift" in RAG_INTENTS


def test_multiple_product_contexts_are_combined() -> None:
    product = SimpleNamespace(
        model_dump=lambda mode: {
            "product_id": 1,
            "product_name": "테스트 상품",
        }
    )

    context = ContextService().build_products_context([product])

    assert "선택 상품 1" in context
    assert "테스트 상품" in context


class FakeCollection:
    def __init__(self) -> None:
        self.query_arguments: dict = {}

    def count(self) -> int:
        return 1

    def query(self, **kwargs):
        self.query_arguments = kwargs
        return {
            "ids": [["chunk-1"]],
            "documents": [["검색 문서"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }


class FakeEmbeddings:
    def create(self, **kwargs):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )


def test_repository_queries_with_openai_embedding() -> None:
    collection = FakeCollection()
    repository = InterpretationRepository(
        collection=collection,
        embedding_client=SimpleNamespace(
            embeddings=FakeEmbeddings()
        ),
        embedding_model="test-embedding-model",
    )

    repository.search(question="증여세", top_k=1)

    assert collection.query_arguments["query_embeddings"] == [
        [0.1, 0.2]
    ]
    assert "query_texts" not in collection.query_arguments


class FakeRepository:
    def search(self, **kwargs):
        return {
            "ids": [["chunk-1"]],
            "documents": [["검색 문서"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }


def test_retrieval_formats_both_search_results() -> None:
    service = RetrievalService(
        interpretation_repository=FakeRepository(),
        law_repository=FakeRepository(),
    )

    context = service.retrieve("증여세")

    assert "국세청 법령해석 사례" in context
    assert "법령해석 1" in context
    assert "관련 법령 원문" in context
    assert "법령 원문 1" in context
