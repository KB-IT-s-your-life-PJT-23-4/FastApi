import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.repositories.interpretation_repository import InterpretationRepository
from app.repositories.law_repository import LawRepository


LAW_INFO_URL = "https://www.law.go.kr/LSW/lsInfoP.do"
ARTICLE_NUMBER_PATTERN = re.compile(r"제\d+조(?:의\d+)?")


@dataclass(frozen=True)
class LawReference:
    law_name: str
    article_no: str
    title: str | None
    url: str


@dataclass(frozen=True)
class RetrievalResult:
    context: str
    references: list[LawReference]


class RetrievalService:
    def __init__(
        self,
        interpretation_repository: InterpretationRepository,
        law_repository: LawRepository,
        interpretation_top_k: int = 4,
        law_top_k: int = 2,
        law_chunk_top_k: int = 10,
    ) -> None:
        self.interpretation_repository = interpretation_repository
        self.law_repository = law_repository
        self.interpretation_top_k = interpretation_top_k
        self.law_top_k = law_top_k
        self.law_chunk_top_k = law_chunk_top_k

    def retrieve(
        self,
        question: str,
    ) -> str:
        return self.retrieve_result(question).context

    def retrieve_result(
        self,
        question: str,
    ) -> RetrievalResult:
        interpretation_result = (
            self.interpretation_repository.search(
                question=question,
                top_k=self.interpretation_top_k,
            )
        )

        law_result = self.law_repository.search(
            question=question,
            top_k=self.law_chunk_top_k,
        )
        grouped_law_result = group_law_results_by_article(
            law_result,
            max_articles=self.law_top_k,
        )

        interpretation_contexts = (
            format_interpretation_context(
                interpretation_result
            )
        )

        law_contexts = format_law_context(grouped_law_result)

        context = "\n\n".join(
            [
                "===== 국세청 법령해석 사례 =====",
                *interpretation_contexts,
                "",
                "===== 관련 법령 원문 =====",
                *law_contexts,
            ]
        )

        return RetrievalResult(
            context=context,
            references=build_law_references(grouped_law_result),
        )

    def find_references_for_citations(
        self,
        citations: list[str],
        existing_references: list[LawReference] | None = None,
    ) -> list[LawReference]:
        """답변 근거에 적힌 조문을 메타데이터에서 직접 찾는다."""
        article_numbers = list(dict.fromkeys(
            article_no
            for citation in citations
            for article_no in ARTICLE_NUMBER_PATTERN.findall(citation)
        ))
        if not article_numbers:
            return existing_references or []

        metadatas = (
            self.law_repository.find_metadatas_by_article_numbers(
                article_numbers
            )
        )
        resolved = build_law_references_from_metadatas(metadatas)
        return merge_law_references(
            existing_references or [],
            resolved,
        )


def convert_article_no_to_jo_no(article_no: str) -> str | None:
    """국가법령정보센터의 조문 번호 형식으로 변환한다."""
    match = re.fullmatch(
        r"\s*제(\d+)조(?:의(\d+))?\s*",
        article_no,
    )
    if match is None:
        return None

    main_number = int(match.group(1))
    branch_number = int(match.group(2) or 0)
    return f"{main_number:04d}{branch_number:02d}"


def build_law_article_url(metadata: dict[str, Any]) -> str:
    """벡터 메타데이터로 특정 법령 조문 URL을 생성한다."""
    mst = str(metadata.get("mst") or "").strip()
    law_id = str(
        metadata.get("law_code")
        or metadata.get("law_id")
        or ""
    ).strip()
    article_no = str(
        metadata.get("article_no")
        or metadata.get("article_label")
        or ""
    ).strip()

    identifier_key = "lsiSeq" if mst else "lsId"
    identifier_value = mst or law_id
    if not identifier_value:
        return str(metadata.get("source_url") or "")

    params = {
        identifier_key: identifier_value,
        "urlMode": "lsInfoP",
    }
    jo_no = convert_article_no_to_jo_no(article_no)
    if jo_no:
        params["joNo"] = jo_no

    return f"{LAW_INFO_URL}?{urlencode(params)}"


def build_law_references(
    search_result: dict[str, Any],
) -> list[LawReference]:
    return build_law_references_from_metadatas(
        get_first_result_list(search_result, "metadatas")
    )


def build_law_references_from_metadatas(
    metadatas: list[dict[str, Any]],
) -> list[LawReference]:
    references: list[LawReference] = []
    seen_urls: set[str] = set()

    for metadata in metadatas:
        metadata = metadata or {}
        url = build_law_article_url(metadata)
        if not url or url in seen_urls:
            continue

        article_no = str(
            metadata.get("article_no")
            or metadata.get("article_label")
            or ""
        )
        law_name = str(metadata.get("law_name") or "")
        if not law_name or not article_no:
            continue

        title = (
            metadata.get("article_title")
            or metadata.get("title")
            or None
        )
        references.append(
            LawReference(
                law_name=law_name,
                article_no=article_no,
                title=str(title) if title else None,
                url=url,
            )
        )
        seen_urls.add(url)

    return references


def merge_law_references(
    *groups: list[LawReference],
) -> list[LawReference]:
    merged: list[LawReference] = []
    seen_urls: set[str] = set()
    for reference in (
        reference
        for group in groups
        for reference in group
    ):
        if reference.url in seen_urls:
            continue
        merged.append(reference)
        seen_urls.add(reference.url)
    return merged

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


def group_law_results_by_article(
    search_result: dict[str, Any],
    max_articles: int = 2,
) -> dict[str, list[list[Any]]]:
    """법령 청크를 조문 단위로 묶고 항·분할 순서대로 합친다."""
    if max_articles <= 0:
        raise ValueError("조문 검색 개수는 1 이상이어야 합니다.")

    ids = get_first_result_list(search_result, "ids")
    documents = get_first_result_list(search_result, "documents")
    metadatas = get_first_result_list(search_result, "metadatas")
    distances = get_first_result_list(search_result, "distances")

    grouped: dict[tuple[str, str], list[tuple[Any, ...]]] = {}

    for chunk_id, document, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):
        metadata = metadata or {}
        key = (
            str(metadata.get("law_id", "")),
            str(metadata.get("article_key", chunk_id)),
        )

        if key not in grouped:
            if len(grouped) >= max_articles:
                continue
            grouped[key] = []

        grouped[key].append(
            (chunk_id, document, metadata, distance)
        )

    grouped_ids: list[str] = []
    grouped_documents: list[str] = []
    grouped_metadatas: list[dict[str, Any]] = []
    grouped_distances: list[float] = []

    for (law_id, article_key), chunks in grouped.items():
        chunks.sort(
            key=lambda item: (
                int(item[2].get("section_index", 0)),
                int(item[2].get("chunk_index", 0)),
            )
        )
        first_metadata = dict(chunks[0][2])
        article_label = str(
            first_metadata.get("article_label", "")
        )
        article_title = str(
            first_metadata.get("article_title", "")
        )
        article_name = article_label
        if article_title:
            article_name += f"({article_title})"

        bodies = [
            _extract_law_body(str(item[1]))
            for item in chunks
        ]
        paragraph_numbers = list(dict.fromkeys(
            str(item[2].get("paragraph_number", ""))
            for item in chunks
            if item[2].get("paragraph_number")
        ))

        first_metadata["paragraph_number"] = ", ".join(
            paragraph_numbers
        )
        first_metadata["grouped_chunk_count"] = len(chunks)
        article_url = build_law_article_url(first_metadata)
        if article_url:
            first_metadata["source_url"] = article_url
        combined_body = "\n\n".join(bodies)

        grouped_ids.append(
            f"law:{law_id}:{article_key}:grouped"
        )
        grouped_documents.append(
            (
                f"[법령명]\n{first_metadata.get('law_name', '')}\n\n"
                f"[조문]\n{article_name}\n\n"
                f"[내용]\n{combined_body}"
            ).strip()
        )
        grouped_metadatas.append(first_metadata)
        grouped_distances.append(
            min(float(item[3]) for item in chunks)
        )

    return {
        "ids": [grouped_ids],
        "documents": [grouped_documents],
        "metadatas": [grouped_metadatas],
        "distances": [grouped_distances],
    }


def _extract_law_body(document: str) -> str:
    marker = "[내용]\n"
    if marker in document:
        return document.split(marker, 1)[1].strip()
    return document.strip()

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
