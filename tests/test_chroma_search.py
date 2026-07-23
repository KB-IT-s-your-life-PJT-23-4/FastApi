from __future__ import annotations

from typing import Any

from app.collectors.nts_interpretation_collector import (
    CHROMA_COLLECTION_NAME,
    CHROMA_PATH,
    collection,
    group_search_results,
    search_interpretations,
)


def print_collection_info() -> None:
    count = collection.count()

    print("=" * 80)
    print("ChromaDB 연결 정보")
    print(f"저장 경로: {CHROMA_PATH}")
    print(f"컬렉션명: {CHROMA_COLLECTION_NAME}")
    print(f"저장된 청크 수: {count}")
    print("=" * 80)

    if count == 0:
        raise RuntimeError(
            "ChromaDB 컬렉션에 저장된 데이터가 없습니다. "
            "먼저 수집기를 실행해 데이터를 적재하세요."
        )


def print_search_results(
    search_result: dict[str, Any],
) -> None:
    ids = search_result.get("ids", [[]])[0]
    documents = search_result.get("documents", [[]])[0]
    metadatas = search_result.get("metadatas", [[]])[0]
    distances = search_result.get("distances", [[]])[0]

    if not ids:
        print("검색 결과가 없습니다.")
        return

    print(f"\n검색 결과: {len(ids)}개\n")

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

        print("-" * 80)
        print(f"[{index}]")
        print(f"거리: {distance:.6f}")
        print(f"청크 ID: {chunk_id}")
        print(
            f"문서 ID: "
            f"{metadata.get('document_id', '')}"
        )
        print(f"제목: {metadata.get('title', '')}")
        print(
            f"안건번호: "
            f"{metadata.get('case_number', '')}"
        )
        print(
            f"해석일자: "
            f"{metadata.get('interpretation_date', '')}"
        )
        print(
            f"해석기관: "
            f"{metadata.get('agency', '')}"
        )
        print(
            f"섹션: "
            f"{metadata.get('section_label', metadata.get('section', ''))}"
        )
        print(
            f"출처: "
            f"{metadata.get('source_url', '')}"
        )
        print("\n본문:")
        print(document)
        print()


def print_grouped_results(
    search_result: dict[str, Any],
) -> None:
    grouped = group_search_results(search_result)

    print("\n" + "=" * 80)
    print(f"문서별 그룹 수: {len(grouped)}")
    print("=" * 80)

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

        metadata = chunks[0]["metadata"]

        print(f"\n[{document_index}] 문서")
        print(f"문서 ID: {document_id}")
        print(f"제목: {metadata.get('title', '')}")
        print(f"최고 유사 거리: {best_distance:.6f}")
        print(f"검색된 청크 수: {len(chunks)}")

        sorted_chunks = sorted(
            chunks,
            key=lambda chunk: chunk["distance"],
        )

        for chunk in sorted_chunks:
            section = chunk["metadata"].get(
                "section_label",
                chunk["metadata"].get("section", ""),
            )

            print(
                f"  - {section}: "
                f"distance={chunk['distance']:.6f}"
            )

def main() -> None:
    print_collection_info()

    question = input(
        "\n검색할 질문을 입력하세요: "
    ).strip()

    if not question:
        raise ValueError("검색 질문을 입력해야 합니다.")

    top_k_input = input(
        "검색할 청크 수를 입력하세요 [기본값 5]: "
    ).strip()

    top_k = int(top_k_input) if top_k_input else 5

    if top_k <= 0:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    print("\n질문 임베딩 생성 및 ChromaDB 검색 중...")

    search_result = search_interpretations(
        question=question,
        top_k=top_k,
    )

    print_search_results(search_result)
    print_grouped_results(search_result)


if __name__ == "__main__":
    main()