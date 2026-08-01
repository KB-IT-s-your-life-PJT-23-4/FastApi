from __future__ import annotations

import os

import chromadb

from app.collectors.law_article_collector import (
    chroma_client,
    collect_and_store_law,
)

LAW_COSINE_COLLECTION_NAME = os.getenv(
    "LAW_COSINE_COLLECTION_NAME",
    "gift_tax_law_articles_cosine",
)


def get_cosine_law_collection(
    collection_name: str = LAW_COSINE_COLLECTION_NAME,
) -> chromadb.Collection:
    return chroma_client.get_or_create_collection(
        name=collection_name,
        configuration={
            "hnsw": {
                "space": "cosine",
            }
        },
        metadata={
            "description": "상속세 및 증여세법 조문 (Cosine)",
        },
    )


def collect_and_store_law_cosine(
    mst: str,
    collection_name: str = LAW_COSINE_COLLECTION_NAME,
) -> None:
    cosine_collection = get_cosine_law_collection(
        collection_name
    )
    collect_and_store_law(
        mst=mst,
        target_collection=cosine_collection,
    )


if __name__ == "__main__":
    collect_and_store_law_cosine(
        mst="276123",
    )
