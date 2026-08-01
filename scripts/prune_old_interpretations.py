from __future__ import annotations

import argparse

from app.collectors.nts_interpretation_collector import (
    CHROMA_COLLECTION_NAME,
    INTERPRETATION_START_DATE,
    chroma_client,
    delete_interpretation_chunks_before,
    find_interpretation_chunk_ids_before,
)
from app.collectors.nts_interpretation_cosine_collector import (
    INTERPRETATION_COSINE_COLLECTION_NAME,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "기준일 이전 국세청 법령해석 청크를 "
            "L2/Cosine 컬렉션에서 정리합니다."
        )
    )
    parser.add_argument(
        "--start-date",
        default=INTERPRETATION_START_DATE,
        help="보존할 시작일(기본값: 2014-01-01)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="지정해야 실제로 삭제합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    collection_names = (
        CHROMA_COLLECTION_NAME,
        INTERPRETATION_COSINE_COLLECTION_NAME,
    )

    for collection_name in collection_names:
        target_collection = chroma_client.get_collection(
            collection_name
        )
        ids_to_delete = find_interpretation_chunk_ids_before(
            target_collection,
            start_date=args.start_date,
        )

        print(
            f"{collection_name}: "
            f"전체={target_collection.count()}개, "
            f"삭제 대상={len(ids_to_delete)}개"
        )

        if not args.apply:
            continue

        deleted_count = delete_interpretation_chunks_before(
            target_collection,
            start_date=args.start_date,
        )
        print(
            f"{collection_name}: {deleted_count}개 삭제 완료, "
            f"잔여={target_collection.count()}개"
        )

    if not args.apply:
        print("dry-run입니다. 실제 삭제는 --apply를 지정하세요.")


if __name__ == "__main__":
    main()
