from typing import Any

import chromadb

class InterpretationRepository:
    def __init__(
        self,
        collection: chromadb.Collection,
        ) -> None:
        self.collection = collection

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
                "법령 해석 컬렉션에 데이터가 없습니다."
            )

        return self.collection.query(
            query_texts=[question],
            n_results=min(top_k, count),
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )
        