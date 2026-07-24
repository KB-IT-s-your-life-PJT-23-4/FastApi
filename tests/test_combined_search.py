from __future__ import annotations

from typing import Any

from app.collectors.nts_interpretation_collector import (
    CHROMA_COLLECTION_NAME as INTERPRETATION_COLLECTION_NAME,
    CHROMA_PATH,
    collection as interpretation_collection,
    group_search_results,
    search_interpretations,
)
from app.collectors.law_article_collector import (
    LAW_CHROMA_COLLECTION_NAME,
    law_collection,
    search_gift_tax_law,
)


def print_collection_info() -> None:
    interpretation_count = interpretation_collection.count()
    law_count = law_collection.count()

    print("=" * 80)
    print("ChromaDB 연결 정보")
    print(f"저장 경로: {CHROMA_PATH}")
    print("-" * 80)
    print(
        f"법령해석 컬렉션: "
        f"{INTERPRETATION_COLLECTION_NAME}"
    )
    print(
        f"법령해석 청크 수: "
        f"{interpretation_count}"
    )
    print("-" * 80)
    print(
        f"법령 원문 컬렉션: "
        f"{LAW_CHROMA_COLLECTION_NAME}"
    )
    print(
        f"법령 원문 청크 수: "
        f"{law_count}"
    )
    print("=" * 80)

    if interpretation_count == 0:
        print(
            "[경고] 법령해석 컬렉션에 "
            "저장된 데이터가 없습니다."
        )

    if law_count == 0:
        print(
            "[경고] 법령 원문 컬렉션에 "
            "저장된 데이터가 없습니다."
        )

    if (
        interpretation_count == 0
        and law_count == 0
    ):
        raise RuntimeError(
            "검색할 ChromaDB 데이터가 없습니다."
        )


def get_result_values(
    search_result: dict[str, Any],
) -> tuple[
    list[str],
    list[str],
    list[dict[str, Any]],
    list[float],
]:
    ids = search_result.get("ids") or [[]]
    documents = search_result.get("documents") or [[]]
    metadatas = search_result.get("metadatas") or [[]]
    distances = search_result.get("distances") or [[]]

    return (
        ids[0] if ids else [],
        documents[0] if documents else [],
        metadatas[0] if metadatas else [],
        distances[0] if distances else [],
    )


def print_interpretation_results(
    search_result: dict[str, Any],
) -> None:
    (
        ids,
        documents,
        metadatas,
        distances,
    ) = get_result_values(search_result)

    print("\n")
    print("#" * 80)
    print("국세청 법령해석 검색 결과")
    print("#" * 80)

    if not ids:
        print("검색 결과가 없습니다.")
        return

    print(f"검색 결과: {len(ids)}개")

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        section = metadata.get(
            "section_label",
            metadata.get("section", ""),
        )

        print("\n" + "-" * 80)
        print(f"[법령해석 {index}]")
        print(f"거리: {distance:.6f}")
        print(f"청크 ID: {chunk_id}")
        print(
            "문서 ID:",
            metadata.get("document_id", ""),
        )
        print(
            "제목:",
            metadata.get("title", ""),
        )
        print(
            "안건번호:",
            metadata.get("case_number", ""),
        )
        print(
            "해석일자:",
            metadata.get(
                "interpretation_date",
                "",
            ),
        )
        print(
            "해석기관:",
            metadata.get("agency", ""),
        )
        print(f"섹션: {section}")
        print(
            "출처:",
            metadata.get("source_url", ""),
        )
        print("\n본문:")
        print(document)


def print_grouped_interpretation_results(
    search_result: dict[str, Any],
) -> None:
    grouped = group_search_results(
        search_result
    )

    print("\n" + "=" * 80)
    print(
        "법령해석 문서별 그룹 결과: "
        f"{len(grouped)}개"
    )
    print("=" * 80)

    if not grouped:
        return

    sorted_groups = sorted(
        grouped.items(),
        key=lambda item: min(
            chunk["distance"]
            for chunk in item[1]
        ),
    )

    for document_index, (
        document_id,
        chunks,
    ) in enumerate(
        sorted_groups,
        start=1,
    ):
        best_distance = min(
            chunk["distance"]
            for chunk in chunks
        )

        metadata = chunks[0]["metadata"] or {}

        print(f"\n[{document_index}] 문서")
        print(f"문서 ID: {document_id}")
        print(
            "제목:",
            metadata.get("title", ""),
        )
        print(
            f"최고 유사 거리: "
            f"{best_distance:.6f}"
        )
        print(
            f"검색된 청크 수: "
            f"{len(chunks)}"
        )

        sorted_chunks = sorted(
            chunks,
            key=lambda chunk: chunk["distance"],
        )

        for chunk in sorted_chunks:
            chunk_metadata = (
                chunk["metadata"] or {}
            )

            section = chunk_metadata.get(
                "section_label",
                chunk_metadata.get(
                    "section",
                    "",
                ),
            )

            print(
                f"  - {section}: "
                f"distance="
                f"{chunk['distance']:.6f}"
            )


def print_law_results(
    search_result: dict[str, Any],
) -> None:
    (
        ids,
        documents,
        metadatas,
        distances,
    ) = get_result_values(search_result)

    print("\n")
    print("#" * 80)
    print("법령 원문 검색 결과")
    print("#" * 80)

    if not ids:
        print("검색 결과가 없습니다.")
        return

    print(f"검색 결과: {len(ids)}개")

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        print("\n" + "-" * 80)
        print(f"[법령 원문 {index}]")
        print(f"거리: {distance:.6f}")
        print(f"청크 ID: {chunk_id}")
        print(
            "법령명:",
            metadata.get("law_name", ""),
        )
        print(
            "조문:",
            metadata.get(
                "article_label",
                "",
            ),
        )
        print(
            "조문 제목:",
            metadata.get(
                "article_title",
                "",
            ),
        )
        print(
            "항:",
            metadata.get(
                "paragraph_number",
                "",
            ),
        )
        print(
            "세법 범위:",
            metadata.get(
                "tax_scope",
                "",
            ),
        )
        print(
            "문서 구분:",
            metadata.get(
                "document_section",
                "",
            ),
        )
        print(
            "조문 시행일:",
            metadata.get(
                "article_effective_date",
                "",
            ),
        )
        print(
            "법령 시행일:",
            metadata.get(
                "effective_date",
                "",
            ),
        )
        print(
            "소관부처:",
            metadata.get(
                "ministry",
                "",
            ),
        )
        print(
            "출처:",
            metadata.get(
                "source_url",
                "",
            ),
        )
        print("\n본문:")
        print(document)


def search_all_sources(
    question: str,
    interpretation_top_k: int,
    law_top_k: int,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    interpretation_result = None
    law_result = None

    if interpretation_collection.count() > 0:
        print(
            "\n국세청 법령해석 검색 중..."
        )

        interpretation_result = (
            search_interpretations(
                question=question,
                top_k=interpretation_top_k,
            )
        )

    if law_collection.count() > 0:
        print(
            "법령 원문 검색 중..."
        )

        law_result = search_gift_tax_law(
            question=question,
            top_k=law_top_k,
        )

    return (
        interpretation_result,
        law_result,
    )


def main() -> None:
    print_collection_info()

    question = input(
        "\n검색할 질문을 입력하세요: "
    ).strip()

    if not question:
        raise ValueError(
            "검색 질문을 입력해야 합니다."
        )

    top_k_input = input(
        "전체 통합 검색 개수 "
        "[기본값 5]: "
    ).strip()

    top_k = (
        int(top_k_input)
        if top_k_input
        else 5
    )

    if top_k <= 0:
        raise ValueError(
            "top_k는 1 이상이어야 합니다."
        )

    print(
        "\n법령 원문과 법령해석 "
        "통합 검색 중..."
    )

    combined_results = search_combined_top_k(
        question=question,
        top_k=top_k,

        # 각 컬렉션에서 후보 10개씩 가져온 후
        # 합쳐서 최종 top_k를 선정
        candidate_count=max(
            top_k * 2,
            10,
        ),
    )

    print_combined_results(
        combined_results
    )
    
def extract_search_items(
    search_result: dict[str, Any],
    source_type: str,
) -> list[dict[str, Any]]:
    ids = search_result.get("ids") or [[]]
    documents = search_result.get("documents") or [[]]
    metadatas = search_result.get("metadatas") or [[]]
    distances = search_result.get("distances") or [[]]

    result_ids = ids[0] if ids else []
    result_documents = (
        documents[0]
        if documents
        else []
    )
    result_metadatas = (
        metadatas[0]
        if metadatas
        else []
    )
    result_distances = (
        distances[0]
        if distances
        else []
    )

    items: list[dict[str, Any]] = []

    for (
        chunk_id,
        document,
        metadata,
        distance,
    ) in zip(
        result_ids,
        result_documents,
        result_metadatas,
        result_distances,
    ):
        items.append({
            "source_type": source_type,
            "chunk_id": chunk_id,
            "document": document,
            "metadata": metadata or {},
            "distance": float(distance),
        })

    return items

def search_combined_top_k(
    question: str,
    top_k: int = 5,
    candidate_count: int = 10,
) -> list[dict[str, Any]]:
    question = question.strip()

    if not question:
        raise ValueError(
            "검색 질문이 비어 있습니다."
        )

    if top_k <= 0:
        raise ValueError(
            "top_k는 1 이상이어야 합니다."
        )

    if candidate_count < top_k:
        candidate_count = top_k

    combined_items: list[
        dict[str, Any]
    ] = []

    # 법령해석 컬렉션 검색
    if interpretation_collection.count() > 0:
        interpretation_result = (
            search_interpretations(
                question=question,
                top_k=min(
                    candidate_count,
                    interpretation_collection.count(),
                ),
            )
        )

        combined_items.extend(
            extract_search_items(
                search_result=interpretation_result,
                source_type="interpretation",
            )
        )

    # 법령 원문 컬렉션 검색
    if law_collection.count() > 0:
        law_result = search_gift_tax_law(
            question=question,
            top_k=min(
                candidate_count,
                law_collection.count(),
            ),
        )

        combined_items.extend(
            extract_search_items(
                search_result=law_result,
                source_type="law",
            )
        )

    if not combined_items:
        return []

    combined_items.sort(
        key=lambda item: item["distance"]
    )

    return combined_items[:top_k]

def print_combined_results(
    results: list[dict[str, Any]],
) -> None:
    print("\n")
    print("#" * 80)
    print("법령 원문 + 법령해석 통합 검색 결과")
    print("#" * 80)

    if not results:
        print("검색 결과가 없습니다.")
        return

    print(
        f"전체 통합 상위 결과: "
        f"{len(results)}개"
    )

    for index, item in enumerate(
        results,
        start=1,
    ):
        source_type = item["source_type"]
        metadata = item["metadata"]
        distance = item["distance"]

        if source_type == "law":
            source_label = "법령 원문"
            title = (
                f"{metadata.get('article_label', '')}"
                f"({metadata.get('article_title', '')})"
            )
        else:
            source_label = "법령해석"
            title = metadata.get(
                "title",
                "",
            )

        print("\n" + "-" * 80)
        print(f"[{index}] {source_label}")
        print(f"거리: {distance:.6f}")
        print(
            f"청크 ID: "
            f"{item['chunk_id']}"
        )
        print(f"제목: {title}")

        if source_type == "law":
            print(
                "법령명:",
                metadata.get("law_name", ""),
            )
            print(
                "항:",
                metadata.get(
                    "paragraph_number",
                    "",
                ),
            )
            print(
                "세법 범위:",
                metadata.get(
                    "tax_scope",
                    "",
                ),
            )
            print(
                "조문 시행일:",
                metadata.get(
                    "article_effective_date",
                    "",
                ),
            )
        else:
            print(
                "문서 ID:",
                metadata.get(
                    "document_id",
                    "",
                ),
            )
            print(
                "안건번호:",
                metadata.get(
                    "case_number",
                    "",
                ),
            )
            print(
                "해석일자:",
                metadata.get(
                    "interpretation_date",
                    "",
                ),
            )
            print(
                "섹션:",
                metadata.get(
                    "section_label",
                    metadata.get(
                        "section",
                        "",
                    ),
                ),
            )

        print(
            "출처:",
            metadata.get("source_url", ""),
        )
        print("\n본문:")
        print(item["document"])

if __name__ == "__main__":
    main()