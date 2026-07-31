from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_chat_service
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ClarificationRequest
)
from app.services.chat_service import ChatService

router = APIRouter(
    prefix="/chat",
    tags=["AI 상담"]
)

@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 상담 질문",
    description=(
        "사용자 질문과 가족 또는 상품 정보를 받아 "
        "증여 관련 AI 답변을 생성합니다."
    )
)
def ask_question(
    request: ChatRequest,
    chat_service: ChatService = Depends(
        get_chat_service
    ),
) -> ChatResponse:
    return chat_service.process(
        request
    )

# continue_after_clarification 개발 필요
# @router.post(
#     "/clarification",
#     response_model=ChatResponse,
#     status_code=status.HTTP_200_OK,
#     summary="추가 질문 답변 제출",
#     description=(
#         "AI가 요청한 추가 확인 질문에 대한 답변을 받아 "
#         "상담을 이어서 처리합니다."
#     )
# )
# def submit_clarification(
#     request: ClarificationRequest,
#     chat_service: ChatService = Depends(
#         get_chat_service
#     )
# ) -> ChatResponse:
#     return chat_service.continue_after_clarification(
#         request
#     )