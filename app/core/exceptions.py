from __future__ import annotations

from typing import Any

class BusinessException(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None
    ) -> None:
        super().__init__(message)

        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ResourceNotFoundException(
    BusinessException
):
    def __init__(
        self,
        message: str = "요청한 데이터를 찾을 수 없습니다.",
        details: Any | None = None
    ) -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=message,
            status_code=404,
            details=details
        )


class CollectionEmptyException(
    BusinessException
):
    def __init__(
        self,
        message: str = (
            "벡터 데이터베이스에 검색할 "
            "데이터가 없습니다."
        ),
        details: Any | None = None,
    ) -> None:
        super().__init__(
            code="VECTOR_COLLECTION_EMPTY",
            message=message,
            status_code=503,
            details=details,
        )

class ExternalApiException(
    BusinessException
):
    def __init__(
        self,
        message: str = (
            "외부 API 호출 중 오류가 발생했습니다."
        ),
        details: Any | None = None,
    ) -> None:
        super().__init__(
            code="EXTERNAL_API_ERROR",
            message=message,
            status_code=502,
            details=details,
        )