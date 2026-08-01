from uuid import uuid4

from app.core.constants import (
    BLOCKED_INTENTS,
    DEFAULT_FACTS,
    RAG_INTENTS
)
from app.schemas.chat import(
    ClarificationRequest,
    ChatRequest,
    ChatResponse
)
from app.services.answer_service import AnswerService
from app.services.clarification_service import ClarificationService
from app.services.context_service import ContextService
from app.services.intent_service import IntentService
from app.services.retrieval_service import RetrievalService
from app.services.fact_normalization_service import (
    normalize_calculation_facts,
)

class ChatService:
    def __init__(
        self,
        *,
        intent_service: IntentService,
        retrieval_service: RetrievalService,
        clarification_service: ClarificationService,
        answer_service: AnswerService,
        context_service: ContextService,
    ) -> None:
        self.intent_service = intent_service
        self.retrieval_service = retrieval_service
        self.clarification_service = clarification_service
        self.answer_service = answer_service
        self.context_service = context_service

    def process(
        self,
        request: ChatRequest
    ) -> ChatResponse:
        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        question = request.question.strip()

        intent_result = self.intent_service.classify(
            question
        )
        intent = intent_result.intent

        #other, jailbreak인 경우 실패
        if intent in BLOCKED_INTENTS:
            return ChatResponse(
                conversation_id= conversation_id,
                status="REJECTED",
                intent=intent,
                answer=(
                    "증여세, 증여 절차, 등록 가족 또는 "
                    "등록 금융상품 관련 질문을 입력해 주세요."
                )
            )

        if intent == "family" and request.family is None:
            return ChatResponse(
                conversation_id=conversation_id,
                status="COMPLETED",
                intent=intent,
                answer=(
                    "등록된 가족 정보를 확인할 수 없습니다. "
                    "가족을 선택한 후 다시 질문해 주세요."
                )
            )

        if intent == "product" and request.product is None:
            return ChatResponse(
                conversation_id=conversation_id,
                status="COMPLETED",
                intent=intent,
                answer=(
                    "등록된 상품 정보를 확인할 수 없습니다. "
                    "상품을 선택한 후 다시 질문해 주세요."
                )
            )

        facts = {
            **DEFAULT_FACTS,
            **intent_result.extracted_facts,
            **request.facts
        }
        if intent in {"family", "assessment"}:
            facts = normalize_calculation_facts(
                facts,
                question=question,
            )
        
        family_context = ""
        product_context = ""
        rag_context = ""

        if request.family is not None:
            family_dict = request.family.model_dump(
                mode="json"
            )

            if intent == "family":
                facts.update(
                    self.context_service.extract_family_facts(
                        family_dict
                    )
                )

            family_context = (
                self.context_service.build_family_context(
                    family_dict
                )
            )

        if request.product is not None and intent == "product":
            product_context = (
                self.context_service.build_product_context(
                    request.product.model_dump(
                        mode="json"
                    )
                )
            )

        if intent in RAG_INTENTS:
            rag_context = self.retrieval_service.retrieve(
                question
            )

        base_context = self.context_service.combine(
            family_context,
            product_context,
            rag_context,
        )

        clarification = (
            self.clarification_service.analyze(
                question=question,
                context=base_context,
                facts=facts,
                intent=intent,
                requires_calculation=(
                    intent_result.requires_calculation
                ),
            )
        )

        for known_fact in clarification.known_facts:
            facts.setdefault(
                known_fact.key,
                known_fact.value,
            )

        if clarification.needs_clarification:
            return ChatResponse(
                conversation_id=conversation_id,
                status="CLARIFICATION_REQUIRED",
                intent=intent,
                requires_calculation=(
                    intent_result.requires_calculation
                ),
                clarification_questions=(
                    clarification.questions
                ),
                facts=facts
            )

        final_context, facts = (
            self.context_service.build_final_context(
                base_context=base_context,
                facts=facts,
                question=question,
                intent=intent,
                requires_calculation=(
                    intent_result.requires_calculation
                )
            )
        )

        answer = self.answer_service.generate(
            question=question,
            context=final_context,
            facts=facts,
            intent=intent,
        )

        return ChatResponse(
            conversation_id=conversation_id,
            status="COMPLETED",
            intent=intent,
            requires_calculation=(
                intent_result.requires_calculation
            ),
            answer=answer,
            facts=facts,
        )

    def continue_after_clarification(
        self,
        request: ClarificationRequest,
    ) -> ChatResponse:
        facts = {
            **DEFAULT_FACTS,
            **request.facts,
            **request.answers,
        }
        intent = request.intent
        if intent in {"family", "assessment"}:
            facts = normalize_calculation_facts(
                facts,
                question=request.question,
            )
        family_context = ""
        product_context = ""
        rag_context = ""

        if request.family is not None:
            family_dict = request.family.model_dump(mode="json")
            if intent == "family":
                facts.update(
                    self.context_service.extract_family_facts(
                        family_dict
                    )
                )
            family_context = (
                self.context_service.build_family_context(
                    family_dict
                )
            )

        if request.product is not None and intent == "product":
            product_context = (
                self.context_service.build_product_context(
                    request.product
                )
            )

        if intent in RAG_INTENTS:
            rag_context = self.retrieval_service.retrieve(
                request.question
            )

        base_context = self.context_service.combine(
            family_context,
            product_context,
            rag_context,
        )
        requires_calculation = request.requires_calculation
        clarification = self.clarification_service.analyze(
            question=request.question,
            context=base_context,
            facts=facts,
            intent=intent,
            requires_calculation=requires_calculation,
        )

        for known_fact in clarification.known_facts:
            facts.setdefault(known_fact.key, known_fact.value)

        if clarification.needs_clarification:
            return ChatResponse(
                conversation_id=request.conversation_id,
                status="CLARIFICATION_REQUIRED",
                intent=intent,
                requires_calculation=requires_calculation,
                clarification_questions=clarification.questions,
                facts=facts,
            )

        final_context, facts = (
            self.context_service.build_final_context(
                base_context=base_context,
                facts=facts,
                question=request.question,
                intent=intent,
                requires_calculation=requires_calculation,
            )
        )
        answer = self.answer_service.generate(
            question=request.question,
            context=final_context,
            facts=facts,
            intent=intent,
        )

        return ChatResponse(
            conversation_id=request.conversation_id,
            status="COMPLETED",
            intent=intent,
            requires_calculation=requires_calculation,
            answer=answer,
            facts=facts,
        )
