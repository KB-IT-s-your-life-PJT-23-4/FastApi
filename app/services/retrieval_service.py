from app.repositories.interpretation_repository import InterpretationRepository
from app.repositories.law_repository import LawRepository
from typing import Any

class RetrievalService:
    def __init__(
        self,
        interpretation_repository: InterpretationRepository,
        law_repository: LawRepository,
        interpretation_top_k: int = 4,
        law_top_k: int = 2,
    ) -> None:
        self.interpretation_repository = interpretation_repository
        self.law_repository = law_repository
        self.interpretation_top_k = interpretation_top_k
        self.law_top_k = law_top_k

    def retrieve(
        self,
        question: str,
    ) -> str:
        interpretation_result = (
            self.interpretation_repository.search(
                question=question,
                top_k=self.interpretation_top_k,
            )
        )

        law_result = self.law_repository.search(
            question=question,
            top_k=self.law_top_k
        )

        interpretation_contexts = (
            format_interpretation_context(
                interpretation_result
            )
        )

        law_contexts = format_law_context(law_result)

        return "\n\n".join(
            [
                "===== 국세청 법령해석 사례 =====",
                *interpretation_contexts,
                "",
                "===== 관련 법령 원문 =====",
                *law_contexts,
            ]
        )

def format_interpretation_context(
    search_result: dict[str, Any],
) -> list[str]:
    """
    국세청 법령해석 검색 결과를 프롬프트용 문자열 목록으로 변환한다.
    """
    ids = get_first_result_list(
        search_result,
        "ids",
    )
    documents = get_first_result_list(
        search_result,
        "documents",
    )
    metadatas = get_first_result_list(
        search_result,
        "metadatas",
    )
    distances = get_first_result_list(
        search_result,
        "distances",
    )

    contexts: list[str] = []

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

        context = f"""
[법령해석 {index}]
자료 유형: 국세청 법령해석
제목: {metadata.get("title", "")}
안건번호: {metadata.get("case_number", "")}
해석일자: {metadata.get("interpretation_date", "")}
해석기관: {metadata.get("agency", "")}
문서 구분: {section}
문서 ID: {metadata.get("document_id", "")}
청크 ID: {chunk_id}
검색 거리: {float(distance):.6f}
출처: {metadata.get("source_url", "")}

내용:
{document}
""".strip()

        contexts.append(context)

    return contexts

def format_law_context(
    search_result: dict[str, Any],
) -> list[str]:
    """
    법령 원문 검색 결과를 프롬프트용 문자열 목록으로 변환한다.
    """
    ids = get_first_result_list(
        search_result,
        "ids",
    )
    documents = get_first_result_list(
        search_result,
        "documents",
    )
    metadatas = get_first_result_list(
        search_result,
        "metadatas",
    )
    distances = get_first_result_list(
        search_result,
        "distances",
    )

    contexts: list[str] = []

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

        article_label = metadata.get(
            "article_label",
            "",
        )

        article_title = metadata.get(
            "article_title",
            "",
        )

        article_name = article_label

        if article_title:
            article_name = (
                f"{article_label}"
                f"({article_title})"
            )

        context = f"""
[법령 원문 {index}]
자료 유형: 법령 원문
법령명: {metadata.get("law_name", "")}
조문: {article_name}
항: {metadata.get("paragraph_number", "")}
조문 시행일: {metadata.get("article_effective_date", "")}
법령 시행일: {metadata.get("effective_date", "")}
세법 범위: {metadata.get("tax_scope", "")}
법령 ID: {metadata.get("law_id", "")}
조문키: {metadata.get("article_key", "")}
청크 ID: {chunk_id}
검색 거리: {float(distance):.6f}
출처: {metadata.get("source_url", "")}

내용:
{document}
""".strip()

        contexts.append(context)

    return contexts

def get_first_result_list(
    search_result: dict[str, Any],
    key: str,
) -> list[Any]:
    """
    ChromaDB query 결과에서 첫 번째 쿼리의 결과 목록을 꺼낸다.

    예:
        result["documents"] == [[문서1, 문서2]]
        반환값 == [문서1, 문서2]
    """
    values = search_result.get(key) or []

    if not values:
        return []

    first = values[0]

    if not isinstance(first, list):
        return []

    return first
