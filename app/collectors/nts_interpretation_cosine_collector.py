from __future__ import annotations

import os

import chromadb

from app.collectors.nts_interpretation_collector import (
    INTERPRETATION_START_DATE,
    chroma_client,
    collect_and_store,
)

INTERPRETATION_COSINE_COLLECTION_NAME = os.getenv(
    "INTERPRETATION_COSINE_COLLECTION_NAME",
    "gift_tax_documents_cosine",
)


def get_cosine_interpretation_collection(
    collection_name: str = (
        INTERPRETATION_COSINE_COLLECTION_NAME
    ),
) -> chromadb.Collection:
    return chroma_client.get_or_create_collection(
        name=collection_name,
        configuration={
            "hnsw": {
                "space": "cosine",
            }
        },
        metadata={
            "description": "국세청 증여세 법령해석 (Cosine)",
        },
    )


def collect_and_store_interpretations_cosine(
    query: str = "증여",
    start_page: int = 1,
    end_page: int = 20,
    collection_name: str = (
        INTERPRETATION_COSINE_COLLECTION_NAME
    ),
    start_date: str = INTERPRETATION_START_DATE,
) -> None:
    cosine_collection = (
        get_cosine_interpretation_collection(
            collection_name
        )
    )
    collect_and_store(
        query=query,
        start_page=start_page,
        end_page=end_page,
        target_collection=cosine_collection,
        start_date=start_date,
    )


if __name__ == "__main__":
    collect_and_store_interpretations_cosine(
        query="증여",
        start_page=1,
        end_page=20,
        start_date=INTERPRETATION_START_DATE,
    )
