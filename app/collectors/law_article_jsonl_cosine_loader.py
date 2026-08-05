from __future__ import annotations

import hashlib
import logging
import os
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)

LAW_JSONL_PATH = Path(
    os.getenv(
        "LAW_JSONL_PATH",
        "../backend/build/law-jsonl/law_article.jsonl",
    )
)

CHROMA_PATH = os.getenv(
    "CHROMA_PATH",
    "/mirizoom/fastapi/storage/chroma",
)

LAW_COLLECTION_NAME = os.getenv(
    "LAW_COLLECTION_NAME",
    "gift_tax_law_articles",
)

OPENAI_EMBEDDING_API_KEY = os.environ[
    "OPENAI_EMBEDDING_API_KEY"
]
OPENAI_EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL",
    "text-embedding-3-small",
)


CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
EMBEDDING_BATCH_SIZE = 50


GIFT_KEYWORDS = (
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

INHERITANCE_KEYWORDS = (
    "상속",
    "상속세",
    "상속인",
    "피상속인",
    "상속재산",
    "상속개시",
    "수유자",
)

def load_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"법령 JSONL 파일이 없습니다: {path}"
        )
    records: list[dict[str, Any]] = []

    with path.open(
        mode="r",
        encoding="utf-8",
    ) as file:
        for line_number, raw_line in enumerate(
            file,
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL {line_number}번째 줄이 "
                    f"올바른 JSON이 아닙니다."
                ) from exc

            source_id = record.get("id")
            text = record.get("text")
            metadata = record.get("metadata")

            if not isinstance(source_id, str) or not source_id:
                raise ValueError(
                    f"{line_number}번째 줄에 id가 없습니다."
                )

            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"{line_number}번째 줄에 text가 없습니다."
                )

            if not isinstance(metadata, dict):
                raise ValueError(
                    f"{line_number}번째 줄의 metadata가 "
                    f"객체가 아닙니다."
                )

            records.append(record)

    logger.info(
        "법령 JSONL 로드 완료 path=%s records=%d",
        path,
        len(records),
    )

    return records

def classify_tax_scope(
    text: str,
) -> str:
    has_gift = any(
        keyword in text
        for keyword in GIFT_KEYWORDS
    )

    has_inheritance = any(
        keyword in text
        for keyword in INHERITANCE_KEYWORDS
    )

    if has_gift and has_inheritance:
        return "both"

    if has_gift:
        return "gift"

    if has_inheritance:
        return "inheritance"

    return "common"


def split_long_text(
        text: str,
        max_chars: int = CHUNK_MAX_CHARS,
        overlap_chars: int = CHUNK_OVERLAP_CHARS,
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

            overlap = current[-overlap_chars:]
            current = f"{overlap}\n{line}".strip()
            continue


        # 한 줄 자체가 max_chars보다 긴 경우
        start = 0

        while start < len(line):
            end = start + max_chars
            chunks.append(line[start:end])

            start = max(
                end - overlap_chars,
                start + 1,
            )

        current = ""

    if current:
        chunks.append(current)

    return chunks

def sanitize_metadata(
        metadata: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    sanitize: dict[
        str,
        str | int | float | bool
    ] = {}

    for key, value in metadata.items():
        if value is None:
            sanitize[key] = ""
        elif isinstance(
            value,
            (str, int, float, bool),
        ):
            sanitize[key] = value
        else:
            sanitize[key] = json.dumps(
                value,
                ensure_ascii=False,
            )

    return sanitize

def extract_body(
    text: str,
    metadata: dict[str, Any],
) -> str:
    """
    JSONL text의 첫 줄에는 이미
    '법령명 제1조(제목)'이 들어 있으므로 제거한다.
    """
    lines = text.strip().splitlines()

    if len(lines) <= 1:
        return text.strip()

    law_name = str(
        metadata.get("law_name") or ""
    )

    if lines[0].startswith(law_name):
        return "\n".join(lines[1:]).strip()

    return text.strip()

def build_document(
    body: str,
    metadata: dict[str, Any],
) -> str:
    law_name = str(metadata.get("law_name") or "")
    article_no = str(metadata.get("article_no") or "")
    title = str(metadata.get("title") or "")

    article_name = article_no

    if title:
        article_name += f"({title})"

    return f"""
[법령명]
{law_name}

[조문]
{article_name}

[내용]
{body}
""".strip()


def build_chunk_id(
    source_id: dict[str, Any],
    chunk_index: int,
    document: str,
) -> str:
    content_hash = hashlib.sha256(
        document.encode("utf-8")
    ).hexdigest()[:12]

    return (
        f"{source_id}:chunk:"
        f"{chunk_index}:{content_hash}"
    )

# 메타 데이터 구조
def build_metadata(
    source_id: str,
    original: dict[str, Any],
    *,
    tax_scope: str,
    chunk_index: int,
    embedding_hash: str,
    metadata_hash: str,
) -> dict[str, str | int | float | bool]:
    metadata = {
        **original,

        # 현재 LawRepository 검색 필수 필드
        "document_section": "article",
        "tax_scope": tax_scope,

        # RetrievalService 조문 그룹핑 필드
        "law_id": original.get("law_code", ""),
        "article_label": original.get("article_no", ""),
        "article_title": original.get("title", ""),
        "section": "article",
        "section_index": 0,
        "chunk_index": chunk_index,
        "paragraph_number": "",

        # 출처 정보
        "source_id": source_id,
        "source_type": "law_article_jsonl",
        "source_url": (
            "https://www.law.go.kr/법령/"
            f"{quote(str(original.get('law_name') or ''))}"
        ),

        # 변경 감지용
        "source_embedding_hash": embedding_hash,
        "source_metadata_hash": metadata_hash
    }

    return sanitize_metadata(metadata)


def create_chunks(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for record in records:
        source_id = record["id"]
        original_text = record["text"]
        original_metadata = record["metadata"]

        (
            embedding_hash,
            metadata_hash
        ) = make_source_hashes(record)

        tax_scope = classify_tax_scope(
            original_text
        )

        body = extract_body(
            original_text,
            original_metadata
        )

        body_chunks = split_long_text(body)

        for chunk_index, body_chunk in enumerate(body_chunks):
            document = build_document(
                body_chunk,
                original_metadata
            )

            chunks.append({
                "id": build_chunk_id(
                    source_id,
                    chunk_index,
                    document,
                ),
                "source_id": source_id,
                "embedding_hash": embedding_hash,
                "metadata_hash": metadata_hash,
                "document": document,
                "metadata": build_metadata(
                    source_id,
                    original_metadata,
                    tax_scope=tax_scope,
                    chunk_index=chunk_index,
                    embedding_hash=embedding_hash,
                    metadata_hash=metadata_hash
                ),
            })

    logger.info(
        "법령 청크 생성 완료 records=%d chunks=%d",
        len(records),
        len(chunks),
    )

    return chunks


def reset_cosine_collection(
    client,
):
    collections = client.list_collections()

    existing_names = {
        item if isinstance(item, str) else item.name
        for item in collections
    }

    if LAW_COLLECTION_NAME in existing_names:
        logger.warning(
            "기존 법령 컬렉션 삭제 collection=%s",
            LAW_COLLECTION_NAME,
        )
        client.delete_collection(
            name=LAW_COLLECTION_NAME
        )

    collection = client.create_collection(
        name=LAW_COLLECTION_NAME,
        configuration={
            "hnsw": {
                "space": "cosine",
            }
        },
        metadata={
            "description" : (
                "MiriZoom 법령 데이터"
            ),
            "distance_metric":"cosine",
            "embedding_model": OPENAI_EMBEDDING_MODEL,
        },
    )

    logger.info(
        "Cosine 컬렉션 초기화 완료 collection = %s",
        LAW_COLLECTION_NAME
    )

    return collection

def get_cosine_collection(
    chroma_client,
):
    return chroma_client.get_or_create_collection(
        name = LAW_COLLECTION_NAME,
        configuration={
            "hnsw": {
                "space":"cosine"
            }
        },
        metadata={
            "description": "law_article.jsonl 기반 세법 데이터",
            "distance_metric": "cosine",
            "embedding_model": OPENAI_EMBEDDING_MODEL,
        },
    )

def embed_and_store(
    collection: chromadb.Collection,
    chunks: list[dict[str, Any]],
) -> None:
    embedding_client = OpenAI(
        api_key=OPENAI_EMBEDDING_API_KEY,
    )

    total = len(chunks)

    for start in range(
        0,
        total,
        EMBEDDING_BATCH_SIZE,
    ):
        batch = chunks[
            start: start + EMBEDDING_BATCH_SIZE
        ]

        documents = [
            item["document"]
            for item in batch
        ]

        response = (
            embedding_client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL,
                input=documents,
            )
        )

        embeddings = [
            item.embedding
            for item in response.data
        ]

        collection.upsert(
            ids=[
                item["id"]
                for item in batch
            ],
            documents=documents,
            embeddings=embeddings,
            metadatas=[
                item["metadata"]
                for item in batch
            ],
        )

        logger.info(
            "임베딩 적재 진행 stored=%d total=%d",
            min(start + len(batch), total),
            total,
        )

# 변경 감지용 해시
def make_hash(
    value: Any,
) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def make_source_hashes(
    record: dict[str, Any],
) -> tuple[str, str]:
    metadata = record["metadata"]

    #이 값이 달라질 경우 임베딩 문자열 변경
    embedding_payload = {
        "text": record["text"],
        "law_name": metadata.get("law_name"),
        "article_no": metadata.get("article_no"),
        "title": metadata.get("title"),

        #모델이나 청킹 기준 변경 시 전체 재임베딩
        "embedding_model": OPENAI_EMBEDDING_MODEL,
        "chunk_max_chars": CHUNK_MAX_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "chunk_version": 1,
    }

    metadata_payload = metadata

    return (
        make_hash(embedding_payload),
        make_hash(metadata_payload)
    )

def main() -> None:
    # JSONL을 먼저 검증한 다음 기존 컬렉션을 삭제한다.
    records = load_jsonl(
        LAW_JSONL_PATH
    )

    if not records:
        raise RuntimeError("JSONL에 법령 데이터가 없습니다.")

    chunks = create_chunks(records)

    if not chunks:
        raise RuntimeError("생성된 법령 청크가 없습니다.")

    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = reset_cosine_collection(
        chroma_client
    )

    embed_and_store(collection, chunks)

    stored_count = collection.count()

    if stored_count != len(chunks):
        raise RuntimeError(
            "법령 청크 수와 ChromaDB 적재 수가 일치하지 않습니다."
            f"chunks={len(chunks)}, stored={stored_count}"
        )

    logger.info(
        "법령 벡터 DB 초기화 완료"
        "collection=%s records=%s "
        "chunks=%d metric=cosine",
        LAW_COLLECTION_NAME,
        len(records),
        stored_count
    )


def load_existing_state(
    collection,
) -> dict[str, dict[str, Any]]:
    result = collection.get(
        include=["metadatas"]
    )

    state: dict[str, dict[str, Any]] = {}

    for chunk_id, metadata in zip(
        result.get("ids") or [],
        result.get("metadatas") or [],
    ):
        metadata = metadata or {}

        source_id = str(
            metadata.get("source_id") or ""
        )

        if not source_id:
            continue

        if source_id not in state:
            state[source_id] = {
                "chunk_ids": [],
                "embedding_hash": metadata.get(
                    "source_embedding_hash",
                    "",
                ),
                "metadata_hash": metadata.get(
                    "source_metadata_hash",
                    "",
                ),
            }

        state[source_id]["chunk_ids"].append(
            chunk_id
        )

    return state

def incremental_sync() -> None:
    records = load_jsonl(
        LAW_JSONL_PATH
    )

    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = get_cosine_collection(
        chroma_client
    )

    existing_state = load_existing_state(
        collection
    )

    current_source_ids = {
        record["id"]
        for record in records
    }

    chunks_to_embed: list[dict[str, Any]] = []
    stale_chunk_ids: list[str] = []

    new_count = 0
    changed_count = 0
    metadata_updated_count = 0
    unchanged_count = 0
    deleted_count = 0

    for record in records:
        source_id = record["id"]

        new_chunks = create_chunks(
            [record]
        )

        if not new_chunks:
            continue

        new_embedding_hash = new_chunks[0][
            "embedding_hash"
        ]
        new_metadata_hash = new_chunks[0][
            "metadata_hash"
        ]

        new_chunk_ids = {
            chunk["id"]
            for chunk in new_chunks
        }

        previous = existing_state.get(
            source_id
        )

        # 새 조문
        if previous is None:
            chunks_to_embed.extend(
                new_chunks
            )
            new_count += 1
            continue

        old_chunk_ids = set(
            previous["chunk_ids"]
        )

        embedding_changed = (
            previous["embedding_hash"]
            != new_embedding_hash
        )

        chunk_structure_changed = (
            old_chunk_ids != new_chunk_ids
        )

        metadata_changed = (
            previous["metadata_hash"]
            != new_metadata_hash
        )

        # 본문, 제목, 청킹 기준 또는 모델이 변경된 경우
        if embedding_changed or chunk_structure_changed:
            chunks_to_embed.extend(
                new_chunks
            )

            # 새 벡터 저장이 완료된 후 삭제할 이전 청크
            stale_chunk_ids.extend(
                old_chunk_ids - new_chunk_ids
            )

            changed_count += 1
            continue

        # metadata만 변경된 경우 OpenAI 호출 없이 갱신
        if metadata_changed:
            collection.update(
                ids=[
                    chunk["id"]
                    for chunk in new_chunks
                ],
                metadatas=[
                    chunk["metadata"]
                    for chunk in new_chunks
                ],
            )

            metadata_updated_count += 1
            continue

        unchanged_count += 1

    # 새로운 조문과 본문 변경 조문만 임베딩
    if chunks_to_embed:
        embed_and_store(
            collection,
            chunks_to_embed,
        )

    # 새 벡터 저장 성공 후 더 이상 사용하지 않는 과거 청크 삭제
    if stale_chunk_ids:
        collection.delete(
            ids=list(set(stale_chunk_ids))
        )

    # JSONL에서 삭제된 조문 처리
    deleted_source_ids = (
        set(existing_state)
        - current_source_ids
    )

    for source_id in deleted_source_ids:
        collection.delete(
            ids=existing_state[source_id][
                "chunk_ids"
            ]
        )
        deleted_count += 1

    logger.info(
        "법령 증분 동기화 완료 "
        "new=%d changed=%d "
        "metadata_updated=%d unchanged=%d "
        "deleted=%d embedded_chunks=%d "
        "collection_count=%d",
        new_count,
        changed_count,
        metadata_updated_count,
        unchanged_count,
        deleted_count,
        len(chunks_to_embed),
        collection.count(),
    )


if __name__ == "__main__":
    incremental_sync()