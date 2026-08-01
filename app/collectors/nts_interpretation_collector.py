from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from itertools import batched

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
CHROMA_PATH = os.getenv("CHROMA_PATH", "storage/chroma")
CHROMA_COLLECTION_NAME = os.getenv(
    "INTERPRETATION_COLLECTION_NAME",
    "gift_tax_documents",
)

LAW_LIST_URL = "https://www.law.go.kr/DRF/lawSearch.do"
NTS_DETAIL_PAGE_URL = "https://taxlaw.nts.go.kr/qt/USEQTA002P.do"
NTS_ACTION_URL = "https://taxlaw.nts.go.kr/action.do"

DETAIL_ACTION_ID = "ASIQTB002PR01"

RAW_DIRECTORY = Path("storage/raw/nts_interpretations")
RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)


@dataclass
class InterpretationListItem:
    document_id: str
    interpretation_serial: str
    title: str
    case_number: str
    interpretation_date: str
    agency: str
    detail_url: str
    data_reference_at: str


@dataclass
class VectorChunk:
    chunk_id: str
    document_id: str
    section: str
    text: str
    metadata: dict[str, Any]


def create_http_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    })

    return session

def extract_ntst_dcm_id(detail_url: str) -> str:
    parsed = urlparse(detail_url)
    query = parse_qs(parsed.query)

    document_ids = query.get("ntstDcmId")

    if not document_ids or not document_ids[0]:
        raise ValueError(
            f"ntstDcmId를 찾을 수 없습니다: {detail_url}"
        )

    return document_ids[0]


def fetch_interpretation_list(
    session: requests.Session,
    query: str,
    start_page: int = 1,
    end_page: int = 20,
    display: int = 10,
) -> list[InterpretationListItem]:
    collected: dict[str, InterpretationListItem] = {}

    for page in range(start_page, end_page + 1):
        params = {
            "OC": LAW_API_OC,
            "target": "ntsCgmExpc",
            "type": "JSON",
            "query": query,
            "display": display,
            "page": page,
        }

        response = session.get(
            LAW_LIST_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        response_data = response.json()
        result = response_data.get("CgmExpc") or {}

        if result.get("resultCode") != "00":
            raise RuntimeError(
                f"목록 조회 실패: {result.get('resultMsg')}"
            )

        items = result.get("cgmExpc") or []

        # 결과가 한 건이면 dict로 반환될 가능성에 대비
        if isinstance(items, dict):
            items = [items]

        for item in items:
            detail_url = item.get("법령해석상세링크", "")

            try:
                document_id = extract_ntst_dcm_id(detail_url)
            except ValueError:
                logging.warning(
                    "상세 ID 추출 실패: %s",
                    detail_url,
                )
                continue

            collected[document_id] = InterpretationListItem(
                document_id=document_id,
                interpretation_serial=str(
                    item.get("법령해석일련번호", "")
                ),
                title=item.get("안건명", "").strip(),
                case_number=item.get("안건번호", "").strip(),
                interpretation_date=item.get("해석일자", "").strip(),
                agency=item.get("해석기관명", "").strip(),
                detail_url=detail_url,
                data_reference_at=item.get(
                    "데이터기준일시",
                    "",
                ).strip(),
            )

        logging.info(
            "목록 %s페이지 수집 완료: 누적 %s건",
            page,
            len(collected),
        )

        # 서버에 과도한 요청을 보내지 않도록 간격 설정
        time.sleep(0.3)

    return list(collected.values())

def build_action_payload(document_id: str) -> dict[str, str]:
    return {
        "actionId": DETAIL_ACTION_ID,
        "paramData": json.dumps(
            {
                "dcmDVO": {
                    "ntstDcmId": document_id,
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def fetch_interpretation_detail(
    session: requests.Session,
    document_id: str,
) -> dict[str, Any]:
    detail_page_url = (
        "https://taxlaw.nts.go.kr/qt/USEQTA002P.do"
    )

    referer = (
        f"{detail_page_url}"
        f"?ntstDcmId={document_id}"
    )

    # 1. 먼저 상세 페이지에 접속해서
    # JSESSIONID 등의 세션 쿠키를 발급받는다.
    page_response = session.get(
        detail_page_url,
        params={
            "ntstDcmId": document_id,
        },
        headers={
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Referer": "https://taxlaw.nts.go.kr/",
        },
        timeout=30,
    )
    page_response.raise_for_status()

    logging.debug(
        "상세 페이지 쿠키: %s",
        session.cookies.get_dict(),
    )

    # 2. application/x-www-form-urlencoded 형식의 Body
    form_data = build_action_payload(document_id)

    headers = {
        "Accept": (
            "application/json, text/javascript, "
            "*/*; q=0.01"
        ),
        "Accept-Language": (
            "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        ),
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
        "Origin": "https://taxlaw.nts.go.kr",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }

    # json=form_data가 아니라 data=form_data 사용
    response = session.post(
        NTS_ACTION_URL,
        data=form_data,
        headers=headers,
        timeout=60,
        allow_redirects=False,
    )

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    logging.info(
        (
            "상세조회 응답: id=%s, status=%s, "
            "content_type=%s, location=%s"
        ),
        document_id,
        response.status_code,
        content_type,
        response.headers.get("Location"),
    )

    if response.is_redirect:
        raise RuntimeError(
            "상세조회 요청이 리다이렉트되었습니다.\n"
            f"document_id={document_id}\n"
            f"status={response.status_code}\n"
            f"location={response.headers.get('Location')}"
        )

    response.raise_for_status()

    body = response.text.lstrip()

    if (
        body.startswith("<!DOCTYPE")
        or body.startswith("<html")
    ):
        error_path = (
            RAW_DIRECTORY
            / f"{document_id}_error.html"
        )

        error_path.write_text(
            response.text,
            encoding="utf-8",
        )

        raise RuntimeError(
            "상세조회가 JSON 대신 HTML을 반환했습니다.\n"
            f"document_id={document_id}\n"
            f"Content-Type={content_type}\n"
            f"오류 응답 저장 위치={error_path}"
        )

    try:
        response_data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "상세조회 응답을 JSON으로 파싱하지 못했습니다.\n"
            f"document_id={document_id}\n"
            f"response={response.text[:500]}"
        ) from exc

    if response_data.get("status") != "SUCCESS":
        raise RuntimeError(
            "상세조회 실패: "
            f"{response_data.get('message')}"
        )

    action_data = (
        response_data
        .get("data", {})
        .get(DETAIL_ACTION_ID)
    )

    if not isinstance(action_data, dict):
        raise RuntimeError(
            f"{DETAIL_ACTION_ID} 결과가 없습니다.\n"
            f"document_id={document_id}"
        )

    document = action_data.get("dcmDVO")

    if not isinstance(document, dict):
        raise RuntimeError(
            "dcmDVO 문서 데이터가 없습니다.\n"
            f"document_id={document_id}"
        )

    returned_document_id = document.get("ntstDcmId")

    if returned_document_id != document_id:
        raise RuntimeError(
            "요청한 문서와 반환된 문서가 다릅니다.\n"
            f"requested={document_id}\n"
            f"returned={returned_document_id}"
        )

    return response_data

def html_to_text(value: Any) -> str:
    if value is None:
        return ""

    decoded = html.unescape(str(value))
    soup = BeautifulSoup(decoded, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)
    text = text.replace("\u00a0", " ")

    # 연속된 공백과 줄바꿈 정리
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()

def extract_detail_content(
    action_data: dict[str, Any],
) -> str:
    file_list = (
        action_data.get("dcmHwpEditorDVOList")
        or []
    )

    if isinstance(file_list, dict):
        file_list = [file_list]

    html_parts: list[str] = []

    for file_item in file_list:
        if not isinstance(file_item, dict):
            continue

        if file_item.get("dcmFleTy") == "html":
            content = html_to_text(
                file_item.get("dcmFleByte")
            )

            if content:
                html_parts.append(content)

    return "\n\n".join(html_parts)

SECTION_PATTERN = re.compile(
    r"(?:^|\n)\s*"
    r"(?:\d+\.\s*)?"
    r"(사실관계|질의내용|회신|"
    r"관련법령\s*및\s*관련\s*사례|관련법령|관련\s*사례)"
    r"\s*(?:\n|$)",
    flags=re.MULTILINE,
)


def split_detail_sections(
    detail_text: str,
) -> dict[str, str]:
    sections: dict[str, str] = {
        "facts": "",
        "question": "",
        "reply_detail": "",
        "legal_basis": "",
        "detail_other": "",
    }

    matches = list(SECTION_PATTERN.finditer(detail_text))

    if not matches:
        sections["detail_other"] = detail_text.strip()
        return sections

    # 첫 번째 제목 이전의 내용
    prefix = detail_text[:matches[0].start()].strip()

    if prefix:
        sections["detail_other"] = prefix

    for index, match in enumerate(matches):
        heading = match.group(1)

        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(detail_text)
        )

        content = detail_text[start:end].strip()

        if heading == "사실관계":
            key = "facts"
        elif heading == "질의내용":
            key = "question"
        elif heading == "회신":
            key = "reply_detail"
        else:
            key = "legal_basis"

        if sections[key]:
            sections[key] += "\n\n" + content
        else:
            sections[key] = content

    return sections

def split_question_reply(
    content: str,
) -> dict[str, str]:
    result = {
        "question": "",
        "reply": "",
        "other": "",
    }

    content = content.strip()

    if not content:
        return result

    question_match = re.search(
        r"\[\s*질의내용\s*\]",
        content,
    )

    reply_match = re.search(
        r"\[\s*회신\s*\]",
        content,
    )

    if question_match and reply_match:
        if question_match.start() < reply_match.start():
            result["other"] = content[
                :question_match.start()
            ].strip()

            result["question"] = content[
                question_match.end()
                :reply_match.start()
            ].strip()

            result["reply"] = content[
                reply_match.end():
            ].strip()

            return result

    if question_match:
        result["other"] = content[
            :question_match.start()
        ].strip()

        result["question"] = content[
            question_match.end():
        ].strip()

        return result

    if reply_match:
        result["other"] = content[
            :reply_match.start()
        ].strip()

        result["reply"] = content[
            reply_match.end():
        ].strip()

        return result

    result["other"] = content
    return result

def format_yyyymmdd(value: Any) -> str:
    text = str(value or "").strip()

    if len(text) != 8 or not text.isdigit():
        return text

    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

def normalize_interpretation(
    list_item: InterpretationListItem,
    response_data: dict[str, Any],
) -> dict[str, Any]:
    action_data = (
        response_data["data"][DETAIL_ACTION_ID]
    )

    document = action_data.get("dcmDVO") or {}

    title = html_to_text(
        document.get("ntstDcmTtl")
    ) or list_item.title

    summary = html_to_text(
        document.get("ntstDcmGistCntn")
    )

    # 질의내용과 회신이 함께 들어 있는 본문
    question_and_reply = html_to_text(
        document.get("ntstDcmCntn")
    )

    # 회신 본문이 아니라 회신번호
    reply_reference = html_to_text(
        document.get("ntstDcmRplyCntn")
    )

    detail_text = extract_detail_content(
        action_data
    )

    detail_sections = split_detail_sections(
        detail_text
    )

    content_sections = split_question_reply(
        question_and_reply
    )

    return {
        "document_id": list_item.document_id,
        "interpretation_serial": (
            list_item.interpretation_serial
        ),
        "title": title,
        "summary": summary,

        # ntstDcmCntn에서 분리한 값
        "question": content_sections["question"],
        "reply": content_sections["reply"],
        "content_other": content_sections["other"],

        # 회신번호
        "reply_reference": reply_reference,

        # 상세 HTML에서 추출한 값
        "facts": detail_sections["facts"],
        "detail_question": detail_sections["question"],
        "legal_basis": detail_sections["legal_basis"],
        "detail_other": detail_sections["detail_other"],

        "case_number": (
            list_item.case_number
            or html_to_text(
                document.get("ntstDcmDscmCntn")
            )
        ),
        "interpretation_date": (
            list_item.interpretation_date
            or format_yyyymmdd(
                document.get("ntstDcmRgtDt")
            )
        ),
        "agency": list_item.agency,
        "source_url": list_item.detail_url,
        "data_reference_at": (
            list_item.data_reference_at
        ),
        "document_type_code": str(
            document.get("ntstDcmClCd") or ""
        ),
        "tax_type_code": str(
            document.get("ntstTlawClCd") or ""
        ),
    }



def save_raw_document(
    document_id: str,
    raw_response: dict[str, Any],
    normalized_document: dict[str, Any],
) -> None:
    target = RAW_DIRECTORY / f"{document_id}.json"

    data = {
        "normalized": normalized_document,
        "raw": raw_response,
    }

    target.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n{2,}", text)
        if paragraph.strip()
    ]

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = (
            f"{current}\n\n{paragraph}".strip()
            if current
            else paragraph
        )

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

            overlap = current[-overlap_chars:]
            current = f"{overlap}\n\n{paragraph}".strip()
        else:
            # 한 문단 자체가 너무 긴 경우 강제 분할
            start = 0

            while start < len(paragraph):
                end = start + max_chars
                chunks.append(paragraph[start:end])
                start = max(end - overlap_chars, start + 1)

            current = ""

    if current:
        chunks.append(current)

    return chunks

def make_chunk_id(
    document_id: str,
    section: str,
    index: int,
    text: str,
) -> str:
    content_hash = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]

    return (
        f"{document_id}:{section}:{index}:"
        f"{content_hash}"
    )

def create_vector_chunks(
    document: dict[str, Any],
) -> list[VectorChunk]:
    document_id = document["document_id"]
    title = document["title"]

    common_metadata = {
        "document_id": document_id,
        "source_type": "nts_tax_interpretation",
        "title": title[:1000],
        "case_number": document["case_number"][:500],
        "interpretation_date": (
            document["interpretation_date"]
        ),
        "agency": document["agency"][:100],
        "source_url": document["source_url"][:2000],
        "tax_type_code": str(
            document.get("tax_type_code", "")
        ),
    }

    chunks: list[VectorChunk] = []

    # 대표 청크: 제목 + 결론 요지
    summary_text = "\n\n".join(
        part
        for part in [
            f"[주제]\n{title}" if title else "",
            (
                f"[결론 요지]\n{document['summary']}"
                if document["summary"]
                else ""
            ),
        ]
        if part
    )

    if summary_text:
        chunks.append(
            VectorChunk(
                chunk_id=make_chunk_id(
                    document_id,
                    "summary",
                    0,
                    summary_text,
                ),
                document_id=document_id,
                section="summary",
                text=summary_text,
                metadata={
                    **common_metadata,
                    "section": "summary",
                    "chunk_index": 0,
                },
            )
        )

    section_fields = {
        "reply": "회신",
        "facts": "사실관계",
        "question": "질의내용",
        "reply_detail": "상세 회신",
        "legal_basis": "관련법령 및 관련 사례",
        "detail_other": "기타 상세내용",
    }

    for field, section_label in section_fields.items():
        content = str(document.get(field) or "").strip()

        if not content:
            continue

        section_chunks = split_long_text(content)

        for index, section_content in enumerate(
            section_chunks
        ):
            # 각 청크에 제목을 반복하여 독립적인 의미를 보존
            text = (
                f"[주제]\n{title}\n\n"
                f"[{section_label}]\n{section_content}"
            )

            chunks.append(
                VectorChunk(
                    chunk_id=make_chunk_id(
                        document_id,
                        field,
                        index,
                        text,
                    ),
                    document_id=document_id,
                    section=field,
                    text=text,
                    metadata={
                        **common_metadata,
                        "section": field,
                        "section_label": section_label,
                        "chunk_index": index,
                    },
                )
            )

    return chunks


openai_client = OpenAI(
    api_key=OPENAI_EMBEDDING_API_KEY,
)


def create_embeddings(
    texts: list[str],
) -> list[list[float]]:
    response = openai_client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=texts,
    )

    return [
        item.embedding
        for item in response.data
    ]

chroma_client = chromadb.PersistentClient(
    path=CHROMA_PATH
)

collection = chroma_client.get_or_create_collection(
    name=CHROMA_COLLECTION_NAME,
    metadata={
        "description": "국세청 증여세 법령해석",
    },
)


def upsert_chunks(
    chunks: list[VectorChunk],
    batch_size: int = 50,
    target_collection: chromadb.Collection | None = None,
) -> None:
    destination = (
        target_collection
        if target_collection is not None
        else collection
    )

    for chunk_batch in batched(chunks, batch_size):
        texts = [chunk.text for chunk in chunk_batch]
        embeddings = create_embeddings(texts)

        destination.upsert(
            ids=[
                chunk.chunk_id
                for chunk in chunk_batch
            ],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                chunk.metadata
                for chunk in chunk_batch
            ],
        )

        logging.info(
            "ChromaDB %s개 청크 저장 완료",
            len(chunk_batch),
        )

def collect_and_store(
    query: str = "증여",
    start_page: int = 1,
    end_page: int = 20,
    target_collection: chromadb.Collection | None = None,
) -> None:
    session = create_http_session()

    list_items = fetch_interpretation_list(
        session=session,
        query=query,
        start_page=start_page,
        end_page=end_page,
        display=10,
    )

    logging.info(
        "상세조회 대상: %s건",
        len(list_items),
    )

    success_count = 0
    failure_count = 0

    for index, item in enumerate(list_items, start=1):
        try:
            raw_response = fetch_interpretation_detail(
                session,
                item.document_id,
            )

            document = normalize_interpretation(
                item,
                raw_response,
            )

            save_raw_document(
                item.document_id,
                raw_response,
                document,
            )

            chunks = create_vector_chunks(document)

            if not chunks:
                logging.warning(
                    "저장할 본문 없음: %s",
                    item.document_id,
                )
                continue

            upsert_chunks(
                chunks,
                target_collection=target_collection,
            )

            success_count += 1

            logging.info(
                "[%s/%s] 저장 완료: %s / 청크 %s개",
                index,
                len(list_items),
                item.title,
                len(chunks),
            )

        except Exception:
            failure_count += 1

            logging.exception(
                "[%s/%s] 처리 실패: %s",
                index,
                len(list_items),
                item.document_id,
            )

        # 내부 사이트에 요청을 몰아서 보내지 않도록 간격 설정
        time.sleep(0.7)

    logging.info(
        "수집 종료: 성공=%s, 실패=%s",
        success_count,
        failure_count,
    )


def search_interpretations(
    question: str,
    top_k: int = 5,
) -> dict[str, Any]:
    query_embedding = create_embeddings(
        [question]
    )[0]

    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

def group_search_results(
    search_result: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    ids = search_result["ids"][0]
    documents = search_result["documents"][0]
    metadatas = search_result["metadatas"][0]
    distances = search_result["distances"][0]

    for chunk_id, text, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):
        document_id = metadata["document_id"]

        grouped.setdefault(document_id, []).append({
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata,
            "distance": distance,
        })

    return grouped

if __name__ == "__main__":
    collect_and_store(
        query="증여",
        start_page=2,
        end_page=20,
    )
