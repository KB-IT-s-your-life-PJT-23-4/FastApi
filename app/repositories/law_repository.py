from typing import Any

import chromadb
from openai import OpenAI

class LawRepository:
    def __init__(
        self,
        collection: chromadb.Collection,
        embedding_client: OpenAI,
        embedding_model: str,
    ) -> None:
        self.collection = collection
        self.embedding_client = embedding_client
        self.embedding_model = embedding_model

    def count(self) -> int:
        return self.collection.count()

    def search(
        self,
        *,
        question: str,
        top_k: int,
    ) -> dict[str, Any]:
        count = self.collection.count()

        if count == 0:
            raise RuntimeError(
                "법령 원문 컬렉션에 데이터가 없습니다."
            )

        query_embedding = self.embedding_client.embeddings.create(
            model=self.embedding_model,
            input=[question],
        ).data[0].embedding

        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            where={
                "$and": [
                    {"document_section": "article"},
                    {
                        "$or": [
                            {"tax_scope": "gift"},
                            {"tax_scope": "both"},
                            {"tax_scope": "common"},
                        ]
                    },
                ]
            },
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )

        
