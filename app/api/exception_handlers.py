from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)

from app.core.exceptions import (
    BusinessException,
    CollectionEmptyException,
    ExternalApiException,
    ResourceNotFoundException
)

logger = logging.getLogger(__name__)

def create_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: object | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success":False,
            "status_code": status_code,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "path": request.url.path,
            "error": {
                "code":code,
                "message": message,
                "details": details
            },
        }
    )


def register_exception_handlers(
    app:FastAPI,
) -> None:
    @app.exception_handler(BusinessException)
    async def handle_business_exception(
        request: Request,
        exc: BusinessException,
    ) -> JSONResponse:
        return create_error_response(
            request=request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details
        )

    @app.exception_handler(
        ResourceNotFoundException
    )
    async def handle_resource_not_found(
        request: Request,
        exc: ResourceNotFoundException,
    ) -> JSONResponse:
        return create_error_response(
            request=request,
            status_code=status.HTTP_404_NOT_FOUND,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(
        CollectionEmptyException
    )
    async def handle_collection_empty(
        request: Request,
        exc: CollectionEmptyException,
    ) -> JSONResponse:
        return create_error_response(
            request=request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )   

    @app.exception_handler(
        ExternalApiException
    )
    async def handle_external_api_exception(
        request: Request,
        exc: ExternalApiException,
    ) -> JSONResponse:
        return create_error_response(
            request=request,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(
        RequestValidationError
    )
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = exc.errors()
        safe_details = [
            {
                "type": error.get("type"),
                "loc": error.get("loc"),
                "msg": error.get("msg"),
            }
            for error in details
        ]
        logger.warning(
            "request_validation_failed path=%s details=%s",
            request.url.path,
            safe_details,
        )
        return create_error_response(
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="REQUEST_VALIDATION_ERROR",
            message="요청 데이터 형식이 올바르지 않습니다.",
            details=details,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        return create_error_response(
            request=request,
            status_code=exc.status_code,
            code="HTTP_ERROR",
            message=str(exc.detail),
        )

    @app.exception_handler(APITimeoutError)
    async def handle_openai_timeout(
        request: Request,
        exc: APITimeoutError,
    ) -> JSONResponse:
        logger.warning(
            "OpenAI API timeout: %s",
            exc,
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="OPENAI_TIMEOUT",
            message=(
                "AI 서버 응답 시간이 초과되었습니다."
            ),
        )

    @app.exception_handler(RateLimitError)
    async def handle_openai_rate_limit(
        request: Request,
        exc: RateLimitError,
    ) -> JSONResponse:
        logger.warning(
            "OpenAI rate limit exceeded: %s",
            exc,
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="OPENAI_RATE_LIMIT",
            message=(
                "AI 요청이 많아 잠시 후 다시 "
                "시도해야 합니다."
            ),
        )

    @app.exception_handler(APIConnectionError)
    async def handle_openai_connection_error(
        request: Request,
        exc: APIConnectionError,
    ) -> JSONResponse:
        logger.exception(
            "OpenAI connection error"
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="OPENAI_CONNECTION_ERROR",
            message="AI 서버에 연결할 수 없습니다.",
        )

    @app.exception_handler(APIStatusError)
    async def handle_openai_status_error(
        request: Request,
        exc: APIStatusError,
    ) -> JSONResponse:
        logger.exception(
            "OpenAI API status error: %s",
            exc.status_code,
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="OPENAI_API_ERROR",
            message="AI 서버 호출 중 오류가 발생했습니다.",
            details={
                "upstream_status": exc.status_code,
            },
        )

    @app.exception_handler(httpx.TimeoutException)
    async def handle_httpx_timeout(
        request: Request,
        exc: httpx.TimeoutException,
    ) -> JSONResponse:
        logger.warning(
            "External HTTP timeout: %s",
            exc,
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="EXTERNAL_API_TIMEOUT",
            message=(
                "외부 서비스 응답 시간이 초과되었습니다."
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled server error",
            exc_info=exc,
        )

        return create_error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message=(
                "서버 내부 오류가 발생했습니다."
            ),
        )
