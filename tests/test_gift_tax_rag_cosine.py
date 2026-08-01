from __future__ import annotations

import os

import pytest

from app.collectors import law_article_collector
from app.collectors import nts_interpretation_collector
from app.collectors.law_article_cosine_collector import (
    get_cosine_law_collection,
)
from app.collectors.nts_interpretation_cosine_collector import (
    get_cosine_interpretation_collection,
)
from app.services.retrieval_service import (
    group_law_results_by_article,
)
from tests import test_gift_tax_rag

COSINE_TEST_QUESTION = (
    "부모가 성년 자녀에게 현금을 증여하면 "
    "증여세가 발생하나요?"
)

ORIGINAL_RETRIEVE_CONTEXT = test_gift_tax_rag.retrieve_context
ORIGINAL_SEARCH_GIFT_TAX_LAW = (
    test_gift_tax_rag.search_gift_tax_law
)


def print_prompt_documents(context: str) -> None:
    print("\n" + "=" * 100)
    print("Cosine RAG 프롬프트 적재 문서")
    print("=" * 100)
    print(context)
    print("=" * 100)


def retrieve_context_with_output(*args, **kwargs):
    result = ORIGINAL_RETRIEVE_CONTEXT(*args, **kwargs)
    context, _, _ = result
    print_prompt_documents(context)
    return result


def search_grouped_law_articles(
    question: str,
    top_k: int = 2,
):
    raw_result = ORIGINAL_SEARCH_GIFT_TAX_LAW(
        question=question,
        top_k=max(10, top_k),
    )
    return group_law_results_by_article(
        raw_result,
        max_articles=top_k,
    )


def configure_cosine_collections():
    """기존 RAG 테스트의 검색 대상을 Cosine 컬렉션으로 교체한다."""
    law_collection = get_cosine_law_collection()
    interpretation_collection = (
        get_cosine_interpretation_collection()
    )

    # 기존 검색 함수는 각 collector 모듈의 전역 컬렉션을 사용한다.
    law_article_collector.law_collection = law_collection
    nts_interpretation_collector.collection = (
        interpretation_collection
    )

    # test_gift_tax_rag.retrieve_context()의 count 검사 대상도 교체한다.
    test_gift_tax_rag.law_collection = law_collection
    test_gift_tax_rag.interpretation_collection = (
        interpretation_collection
    )
    test_gift_tax_rag.search_gift_tax_law = (
        search_grouped_law_articles
    )

    return law_collection, interpretation_collection


def require_cosine_integration_test() -> None:
    if os.getenv("RUN_COSINE_RAG_TEST") != "1":
        pytest.skip(
            "RUN_COSINE_RAG_TEST=1일 때만 Cosine RAG 통합 테스트를 실행합니다."
        )


def test_cosine_collections_and_search() -> None:
    require_cosine_integration_test()
    law_collection, interpretation_collection = (
        configure_cosine_collections()
    )

    assert law_collection.configuration_json["hnsw"]["space"] == (
        "cosine"
    )
    assert interpretation_collection.configuration_json[
        "hnsw"
    ]["space"] == "cosine"
    assert law_collection.count() > 0
    assert interpretation_collection.count() > 0

    context, interpretation_result, law_result = (
        retrieve_context_with_output(
            question=COSINE_TEST_QUESTION,
            interpretation_top_k=4,
            law_top_k=2,
        )
    )

    assert context
    assert interpretation_result["documents"][0]
    assert law_result["documents"][0]
    assert interpretation_result["distances"][0]
    assert law_result["distances"][0]
    assert all(
        metadata["grouped_chunk_count"] >= 1
        for metadata in law_result["metadatas"][0]
    )


def main() -> None:
    law_collection, interpretation_collection = (
        configure_cosine_collections()
    )

    print(
        "Cosine 법령 컬렉션:",
        law_collection.name,
        f"({law_collection.count()}개)",
    )
    print(
        "Cosine 법령해석 컬렉션:",
        interpretation_collection.name,
        f"({interpretation_collection.count()}개)",
    )

    test_gift_tax_rag.retrieve_context = (
        retrieve_context_with_output
    )
    test_gift_tax_rag.main()


if __name__ == "__main__":
    main()
