from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.collectors import law_article_cosine_collector
from app.collectors import nts_interpretation_cosine_collector
from app.collectors.nts_interpretation_collector import (
    find_interpretation_chunk_ids_before,
    is_interpretation_on_or_after,
    parse_interpretation_date,
)
from app.core.constants import RAG_INTENTS
from app.data.gift_tax_rules import (
    GIFT_DEDUCTION_TABLE,
    GIFT_TAX_RATE_TABLE,
)
from app.main import app
from app.prompts.answer import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt,
)
from app.prompts.context import build_gift_tax_rule_context
from app.repositories.interpretation_repository import (
    InterpretationRepository,
)
from app.services.context_service import ContextService
from app.services.fact_normalization_service import (
    extract_calculation_facts_from_question,
    normalize_calculation_facts,
)
from app.services.retrieval_service import (
    RetrievalService,
    group_law_results_by_article,
)


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_chat_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/clarification" in paths


def test_answer_prompt_uses_conversational_style() -> None:
    prompt = build_final_answer_prompt(
        question="증여세가 무엇인가요?",
        context="상속세 및 증여세법 제2조",
        additional_facts={},
        intent="concept",
    )

    assert "첫 문장에서 사용자의 질문에 바로 답하세요" in (
        FINAL_ANSWER_SYSTEM_PROMPT
    )
    assert "자연스럽고 친절한 존댓말" in (
        FINAL_ANSWER_SYSTEM_PROMPT
    )
    assert "문서 전문, 청크 ID, 검색 거리" in prompt
    assert "필요한 경우에만 짧은 예시" in prompt


def test_question_facts_override_confirmation_answers() -> None:
    question = (
        "부모가 22세 성년 자녀에게 "
        "6000만원을 증여하면 세금이 얼마인가요?"
    )
    extracted = extract_calculation_facts_from_question(
        question
    )
    facts = normalize_calculation_facts(
        {
            "gift_amount": "맞음",
            "relationship_type": "부모",
            "recipient_age": "22세",
            "recipient_is_minor": "맞음",
            "has_previous_gifts": False,
        },
        question=question,
    )

    assert extracted["gift_amount"] == 60_000_000
    assert extracted["recipient_is_minor"] is False
    assert facts["gift_amount"] == 60_000_000
    assert facts["recipient_age"] == 22
    assert facts["recipient_is_minor"] is False
    assert facts["relationship_type"] == (
        "parent_to_adult_child"
    )


def test_adult_child_deduction_is_explicit_in_context() -> None:
    context = build_gift_tax_rule_context(
        rate_table=GIFT_TAX_RATE_TABLE,
        deduction_table=GIFT_DEDUCTION_TABLE,
        relationship_type="parent_to_adult_child",
    )

    assert "공제 한도: 50,000,000원 (5,000만원)" in context
    assert "5,000,000원(500만원)이 아닙니다" in context


def test_minor_child_deduction_is_explicit_in_context() -> None:
    context = build_gift_tax_rule_context(
        rate_table=GIFT_TAX_RATE_TABLE,
        deduction_table=GIFT_DEDUCTION_TABLE,
        relationship_type="parent_to_minor_child",
    )

    assert "공제 한도: 20,000,000원 (2,000만원)" in context
    assert "2,000,000원(200만원)이 아닙니다" in context


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


def test_law_chunks_are_grouped_by_article() -> None:
    search_result = {
        "ids": [["article-2", "article-1", "other"]],
        "documents": [[
            "[내용]\n② 두 번째 항",
            "[내용]\n① 첫 번째 항",
            "[내용]\n다른 조문",
        ]],
        "metadatas": [[
            {
                "law_id": "law-1",
                "article_key": "article-1",
                "law_name": "테스트법",
                "article_label": "제1조",
                "section_index": 2,
                "chunk_index": 0,
                "paragraph_number": "②",
            },
            {
                "law_id": "law-1",
                "article_key": "article-1",
                "law_name": "테스트법",
                "article_label": "제1조",
                "section_index": 1,
                "chunk_index": 0,
                "paragraph_number": "①",
            },
            {
                "law_id": "law-1",
                "article_key": "article-2",
                "law_name": "테스트법",
                "article_label": "제2조",
                "section_index": 0,
                "chunk_index": 0,
                "paragraph_number": "",
            },
        ]],
        "distances": [[0.2, 0.3, 0.4]],
    }

    grouped = group_law_results_by_article(
        search_result,
        max_articles=2,
    )

    assert len(grouped["documents"][0]) == 2
    first_document = grouped["documents"][0][0]
    assert first_document.index("① 첫 번째 항") < (
        first_document.index("② 두 번째 항")
    )
    assert grouped["metadatas"][0][0][
        "grouped_chunk_count"
    ] == 2
    assert grouped["distances"][0][0] == 0.2


def test_cosine_collectors_create_hnsw_cosine_collections(
    monkeypatch,
) -> None:
    calls: list[dict] = []
    sentinel = object()

    class FakeChromaClient:
        def get_or_create_collection(self, **kwargs):
            calls.append(kwargs)
            return sentinel

    fake_client = FakeChromaClient()
    monkeypatch.setattr(
        law_article_cosine_collector,
        "chroma_client",
        fake_client,
    )
    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "chroma_client",
        fake_client,
    )

    assert (
        law_article_cosine_collector.get_cosine_law_collection(
            "law-cosine-test"
        )
        is sentinel
    )
    assert (
        nts_interpretation_cosine_collector.
        get_cosine_interpretation_collection(
            "interpretation-cosine-test"
        )
        is sentinel
    )

    assert [call["name"] for call in calls] == [
        "law-cosine-test",
        "interpretation-cosine-test",
    ]
    assert all(
        call["configuration"]["hnsw"]["space"]
        == "cosine"
        for call in calls
    )


def test_interpretation_date_cutoff() -> None:
    assert parse_interpretation_date("2014.01.01") is not None
    assert is_interpretation_on_or_after("2014-01-01")
    assert is_interpretation_on_or_after("20140102")
    assert not is_interpretation_on_or_after("2013-12-31")
    assert not is_interpretation_on_or_after("")


def test_cosine_collector_forwards_start_date(monkeypatch) -> None:
    target_collection = object()
    received: dict = {}

    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "get_cosine_interpretation_collection",
        lambda collection_name: target_collection,
    )
    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "collect_and_store",
        lambda **kwargs: received.update(kwargs),
    )

    collect_cosine = (
        nts_interpretation_cosine_collector.
        collect_and_store_interpretations_cosine
    )
    collect_cosine(
        query="증여",
        start_page=1,
        end_page=2,
        start_date="2014-01-01",
    )

    assert received["target_collection"] is target_collection
    assert received["start_date"] == "2014-01-01"


def test_old_interpretation_chunks_are_selected_for_deletion() -> None:
    collection = SimpleNamespace(
        get=lambda include: {
            "ids": ["old", "cutoff", "new", "unknown"],
            "metadatas": [
                {"interpretation_date": "2013-12-31"},
                {"interpretation_date": "2014-01-01"},
                {"interpretation_date": "2020-05-01"},
                {"interpretation_date": ""},
            ],
        }
    )

    ids = find_interpretation_chunk_ids_before(collection)

    assert ids == ["old"]
