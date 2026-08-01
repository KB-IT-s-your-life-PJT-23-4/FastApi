from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Any
from collections import Counter

import chromadb
import requests
from dotenv import load_dotenv
from openai import OpenAI
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


LAW_API_OC = os.environ["LAW_API_OC"]

OPENAI_EMBEDDING_API_KEY = os.environ[
    "OPENAI_EMBEDDING_API_KEY"
]

OPENAI_EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL",
    "text-embedding-3-small",
)

CHROMA_PATH = os.getenv(
    "CHROMA_PATH",
    "storage/chroma",
)

LAW_CHROMA_COLLECTION_NAME = os.getenv(
    "LAW_COLLECTION_NAME",
    "gift_tax_law_articles",
)

LAW_SERVICE_URL = (
    "https://www.law.go.kr/DRF/lawService.do"
)

RAW_DIRECTORY = Path(
    "storage/raw/laws"
)
RAW_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)


@dataclass
class LawChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


def create_http_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.5,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(
        max_retries=retry,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    })

    return session

def fetch_law(
    session: requests.Session,
    mst: str,
) -> dict[str, Any]:
    response = session.get(
        LAW_SERVICE_URL,
        params={
            "OC": LAW_API_OC,
            "target": "law",
            "type": "JSON",
            "MST": mst,
        },
        timeout=60,
    )

    response.raise_for_status()

    try:
        response_data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "법령 API 응답이 JSON이 아닙니다.\n"
            f"status={response.status_code}\n"
            f"response={response.text[:500]}"
        ) from exc

    law = response_data.get("법령")

    if not isinstance(law, dict):
        raise RuntimeError(
            "응답에서 법령 데이터를 찾을 수 없습니다."
        )

    return response_data

def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]

def flatten_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return clean_text(value)

    if isinstance(value, list):
        parts = [
            flatten_text(item)
            for item in value
        ]

        return "\n".join(
            part
            for part in parts
            if part
        )

    if isinstance(value, dict):
        parts = [
            flatten_text(item)
            for item in value.values()
        ]

        return "\n".join(
            part
            for part in parts
            if part
        )

    return clean_text(str(value))

def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")

    # HTML 이미지 태그 제거
    text = re.sub(
        r"<img\b[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text,
    )

    return text.strip()

def classify_tax_scope(
    article: dict[str, Any],
) -> str:
    """
    조문 내용을 기준으로 증여·상속 관련 범위를 분류한다.

    gift:
        증여 관련 표현만 있는 조문

    inheritance:
        상속 관련 표현만 있는 조문

    both:
        상속과 증여 표현이 모두 있는 조문

    common:
        상속·증여 키워드가 명확하지 않은 공통 조문
    """
    searchable_text = flatten_text({
        "title": article.get("조문제목"),
        "content": article.get("조문내용"),
        "paragraphs": article.get("항"),
        "reference": article.get("조문참고자료"),
    })

    gift_keywords = (
        "증여",
        "증여세",
        "증여자",
        "수증자",
        "증여재산",
        "증여재산가액",
        "증여받",
        "증여의제",
        "증여추정",
    )

    inheritance_keywords = (
        "상속",
        "상속세",
        "상속인",
        "피상속인",
        "상속재산",
        "상속개시",
        "수유자",
    )

    has_gift = any(
        keyword in searchable_text
        for keyword in gift_keywords
    )

    has_inheritance = any(
        keyword in searchable_text
        for keyword in inheritance_keywords
    )

    if has_gift and has_inheritance:
        return "both"

    if has_gift:
        return "gift"

    if has_inheritance:
        return "inheritance"

    return "common"

def extract_law_metadata(
    response_data: dict[str, Any],
    mst: str,
) -> dict[str, Any]:
    law = response_data["법령"]
    basic = law.get("기본정보") or {}

    ministry = basic.get("소관부처") or {}
    law_type = basic.get("법종구분") or {}

    return {
        "mst": str(mst),
        "law_key": str(
            law.get("법령키") or ""
        ),
        "law_id": str(
            basic.get("법령ID") or ""
        ),
        "law_name": str(
            basic.get("법령명_한글") or ""
        ),
        "law_type": str(
            law_type.get("content")
            if isinstance(law_type, dict)
            else law_type
        ),
        "promulgation_number": str(
            basic.get("공포번호") or ""
        ),
        "promulgation_date": format_date(
            basic.get("공포일자")
        ),
        "effective_date": format_date(
            basic.get("시행일자")
        ),
        "revision_type": str(
            basic.get("제개정구분") or ""
        ),
        "ministry": str(
            ministry.get("content")
            if isinstance(ministry, dict)
            else ministry
        ),
        "source_type": "law_article",
        "source_url": (
            "https://www.law.go.kr/법령/"
            f"{basic.get('법령명_한글', '')}"
        ),
    }

def format_date(value: Any) -> str:
    text = str(value or "").strip()

    if len(text) != 8 or not text.isdigit():
        return text

    return (
        f"{text[:4]}-"
        f"{text[4:6]}-"
        f"{text[6:8]}"
    )

def render_item(
    item: dict[str, Any],
) -> str:
    parts: list[str] = []

    item_content = flatten_text(
        item.get("호내용")
    )

    if item_content:
        parts.append(item_content)

    subitems = ensure_list(
        item.get("목")
    )

    for subitem in subitems:
        if not isinstance(subitem, dict):
            continue

        subitem_content = flatten_text(
            subitem.get("목내용")
        )

        if subitem_content:
            parts.append(subitem_content)

    return "\n".join(parts).strip()

def render_paragraph(
    paragraph: dict[str, Any],
) -> str:
    parts: list[str] = []

    paragraph_content = flatten_text(
        paragraph.get("항내용")
    )

    if paragraph_content:
        parts.append(paragraph_content)

    items = ensure_list(
        paragraph.get("호")
    )

    for item in items:
        if not isinstance(item, dict):
            continue

        rendered = render_item(item)

        if rendered:
            parts.append(rendered)

    return "\n".join(parts).strip()

def make_article_label(
    article: dict[str, Any],
) -> str:
    article_number = str(
        article.get("조문번호") or ""
    ).strip()

    branch_number = str(
        article.get("조문가지번호") or ""
    ).strip()

    if branch_number:
        return (
            f"제{article_number}조의"
            f"{branch_number}"
        )

    if article_number:
        return f"제{article_number}조"

    return ""

def create_article_chunks(
    response_data: dict[str, Any],
    mst: str,
) -> list[LawChunk]:
    law = response_data["법령"]

    metadata = extract_law_metadata(
        response_data=response_data,
        mst=mst,
    )

    law_name = metadata["law_name"]

    article_container = (
        law.get("조문") or {}
    )

    article_units = ensure_list(
        article_container.get("조문단위")
    )

    chunks: list[LawChunk] = []

    for article in article_units:
        if not isinstance(article, dict):
            continue

        article_type = str(
            article.get("조문여부") or ""
        )

        # 장·절 제목은 제외하고 실제 조문만 적재
        if article_type != "조문":
            continue

        # 저장 제외 조건이 아니라 metadata 분류용
        tax_scope = classify_tax_scope(
            article
        )

        article_key = str(
            article.get("조문키") or ""
        ).strip()

        article_label = make_article_label(
            article
        )

        article_title = flatten_text(
            article.get("조문제목")
        )

        article_content = flatten_text(
            article.get("조문내용")
        )

        article_reference = flatten_text(
            article.get("조문참고자료")
        )

        article_effective_date = format_date(
            article.get("조문시행일자")
        )

        article_metadata = {
            **metadata,

            # 검색 대상 구분
            "document_section": "article",
            "tax_scope": tax_scope,

            # 조문 식별정보
            "article_key": article_key,
            "article_number": str(
                article.get("조문번호") or ""
            ).strip(),
            "article_branch_number": str(
                article.get("조문가지번호") or ""
            ).strip(),
            "article_label": article_label,
            "article_title": article_title,

            # 법령 적용 정보
            "article_effective_date": (
                article_effective_date
            ),
            "article_changed": str(
                article.get("조문변경여부") or ""
            ).strip(),
        }

        paragraphs = ensure_list(
            article.get("항")
        )

        # 항이 없는 조문은 조문 전체를 하나의 의미 단위로 저장
        if not paragraphs:
            body = article_content

            if article_reference:
                body = (
                    f"{body}\n\n"
                    f"[개정 참고]\n"
                    f"{article_reference}"
                ).strip()

            if not body:
                continue

            add_split_chunks(
                chunks=chunks,
                law_name=law_name,
                article_label=article_label,
                article_title=article_title,
                section="article",
                section_index=0,
                body=body,
                metadata={
                    **article_metadata,
                    "paragraph_number": "",
                },
            )

            continue

        # 항이 있는 조문은 항 단위로 저장
        for paragraph_index, paragraph in enumerate(
            paragraphs,
            start=1,
        ):
            if not isinstance(paragraph, dict):
                continue

            paragraph_number = flatten_text(
                paragraph.get("항번호")
            )

            paragraph_body = render_paragraph(
                paragraph
            )

            if not paragraph_body:
                continue

            add_split_chunks(
                chunks=chunks,
                law_name=law_name,
                article_label=article_label,
                article_title=article_title,
                section="paragraph",
                section_index=paragraph_index,
                body=paragraph_body,
                metadata={
                    **article_metadata,
                    "paragraph_number": (
                        paragraph_number
                    ),
                },
            )

    return chunks

def split_long_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    text = text.strip()

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    chunks: list[str] = []
    current = ""

    for line in lines:
        candidate = (
            f"{current}\n{line}".strip()
            if current
            else line
        )

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

            overlap = current[
                -overlap_chars:
            ]

            current = (
                f"{overlap}\n{line}"
            ).strip()
        else:
            start = 0

            while start < len(line):
                end = start + max_chars

                chunks.append(
                    line[start:end]
                )

                start = max(
                    end - overlap_chars,
                    start + 1,
                )

            current = ""

    if current:
        chunks.append(current)

    return chunks

def add_split_chunks(
    chunks: list[LawChunk],
    law_name: str,
    article_label: str,
    article_title: str,
    section: str,
    section_index: int,
    body: str,
    metadata: dict[str, Any],
) -> None:
    body_chunks = split_long_text(body)

    for chunk_index, body_chunk in enumerate(
        body_chunks
    ):
        heading = article_label

        if article_title:
            heading += f"({article_title})"

        text = (
            f"[법령명]\n{law_name}\n\n"
            f"[조문]\n{heading}\n\n"
            f"[내용]\n{body_chunk}"
        ).strip()

        chunk_id = make_chunk_id(
            law_id=metadata["law_id"],
            article_key=metadata["article_key"],
            section=section,
            section_index=section_index,
            chunk_index=chunk_index,
            text=text,
        )

        chunks.append(
            LawChunk(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    **metadata,
                    "section": section,
                    "section_index": (
                        section_index
                    ),
                    "chunk_index": chunk_index,
                },
            )
        )

def make_chunk_id(
    law_id: str,
    article_key: str,
    section: str,
    section_index: int,
    chunk_index: int,
    text: str,
) -> str:
    text_hash = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]

    return (
        f"law:{law_id}:"
        f"{article_key}:"
        f"{section}:"
        f"{section_index}:"
        f"{chunk_index}:"
        f"{text_hash}"
    )

embedding_client = OpenAI(
    api_key=OPENAI_EMBEDDING_API_KEY,
)

def create_embeddings(
    texts: list[str],
) -> list[list[float]]:
    if not texts:
        return []

    response = (
        embedding_client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=texts,
        )
    )

    return [
        item.embedding
        for item in response.data
    ]

chroma_client = chromadb.PersistentClient(
    path=CHROMA_PATH,
)

law_collection = (
    chroma_client.get_or_create_collection(
        name=LAW_CHROMA_COLLECTION_NAME,
        metadata={
            "description": (
                "상속세 및 증여세법 조문"
            ),
        },
    )
)

def upsert_law_chunks(
    chunks: list[LawChunk],
    batch_size: int = 50,
) -> None:
    if not chunks:
        logging.warning(
            "저장할 법령 청크가 없습니다."
        )
        return

    for chunk_batch in batched(
        chunks,
        batch_size,
    ):
        texts = [
            chunk.text
            for chunk in chunk_batch
        ]

        embeddings = create_embeddings(
            texts
        )

        law_collection.upsert(
            ids=[
                chunk.chunk_id
                for chunk in chunk_batch
            ],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                sanitize_metadata(
                    chunk.metadata
                )
                for chunk in chunk_batch
            ],
        )

        logging.info(
            "법령 청크 %s개 저장 완료",
            len(chunk_batch),
        )

def sanitize_metadata(
    metadata: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    result: dict[
        str,
        str | int | float | bool
    ] = {}

    for key, value in metadata.items():
        if value is None:
            result[key] = ""
        elif isinstance(
            value,
            (str, int, float, bool),
        ):
            result[key] = value
        else:
            result[key] = json.dumps(
                value,
                ensure_ascii=False,
            )

    return result

def save_raw_law(
    response_data: dict[str, Any],
    mst: str,
) -> None:
    target = RAW_DIRECTORY / f"{mst}.json"

    target.write_text(
        json.dumps(
            response_data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logging.info(
        "법령 원본 저장 완료: %s",
        target,
    )

def log_chunk_statistics(
    chunks: list[LawChunk],
) -> None:
    scope_counter = Counter(
        str(
            chunk.metadata.get(
                "tax_scope",
                "unknown",
            )
        )
        for chunk in chunks
    )

    section_counter = Counter(
        str(
            chunk.metadata.get(
                "section",
                "unknown",
            )
        )
        for chunk in chunks
    )

    logging.info(
        "법령 청크 전체 개수: %s",
        len(chunks),
    )

    logging.info(
        "세목 범위별 청크: %s",
        dict(scope_counter),
    )

    logging.info(
        "청크 구분별 개수: %s",
        dict(section_counter),
    )

def search_gift_tax_law(
    question: str,
    top_k: int = 5,
) -> dict[str, Any]:
    question = question.strip()

    if not question:
        raise ValueError(
            "검색 질문이 비어 있습니다."
        )

    if top_k <= 0:
        raise ValueError(
            "top_k는 1 이상이어야 합니다."
        )

    collection_count = law_collection.count()

    if collection_count == 0:
        raise RuntimeError(
            "법령 원문 컬렉션에 저장된 데이터가 없습니다."
        )

    query_embedding = create_embeddings(
        [question]
    )[0]

    return law_collection.query(
        query_embeddings=[
            query_embedding
        ],
        n_results=min(
            top_k,
            collection_count,
        ),
        where={
            "$and": [
                {
                    "document_section": "article"
                },
                {
                    "$or": [
                        {
                            "tax_scope": "gift"
                        },
                        {
                            "tax_scope": "both"
                        },
                        {
                            "tax_scope": "common"
                        },
                    ]
                },
            ]
        },
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

def collect_and_store_law(
    mst: str,
) -> None:
    session = create_http_session()

    logging.info(
        "법령 조회 시작: MST=%s",
        mst,
    )

    response_data = fetch_law(
        session=session,
        mst=mst,
    )

    # API 조회 성공 후 원본부터 저장
    save_raw_law(
        response_data=response_data,
        mst=mst,
    )

    chunks = create_article_chunks(
        response_data=response_data,
        mst=mst,
    )

    if not chunks:
        raise RuntimeError(
            "생성된 법령 청크가 없습니다."
        )

    logging.info(
        "법령 청크 생성 완료: %s개",
        len(chunks),
    )

    log_chunk_statistics(chunks)

    upsert_law_chunks(chunks)

    logging.info(
        "법령 ChromaDB 저장 완료: "
        "MST=%s, 청크=%s개",
        mst,
        len(chunks),
    )

if __name__ == "__main__":
    collect_and_store_law(
        mst="276123",
    )
