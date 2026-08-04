from openai import OpenAI

from app.core.constants import CLARIFICATION_FACT_DATA_TYPES
from app.schemas.chat import ClarificationResult
from app.services.fact_normalization_service import (
    is_unknown_value,
    means_no_previous_gifts,
)
from app.prompts.clarification import (
    CLARIFICATION_SYSTEM_PROMPT,
    CLARIFICATION_SCHEMA,
    build_clarification_prompt,
    )

PREVIOUS_GIFT_DETAIL_KEYS = {
    "previous_gift_amount",
    "previous_gift_date",
    "previous_gift_same_donor",
}


def is_fact_satisfied(
    key: str,
    facts: dict,
) -> bool:
    if (
        key in PREVIOUS_GIFT_DETAIL_KEYS
        and means_no_previous_gifts(
            facts.get("has_previous_gifts")
        )
    ):
        return True

    return (
        key in facts
        and not is_unknown_value(facts.get(key))
    )


class ClarificationService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    def analyze(
        self,
        *,
        question: str,
        context: str,
        facts: dict,
        intent: str,
        requires_calculation: bool,
    ) -> ClarificationResult:
        if intent not in {"assessment", "family"}:
            return ClarificationResult(
                needs_clarification=False,
                questions=[],
                known_facts=[],
                reason="추가 확인 대상이 아닙니다."
            )

        prompt = build_clarification_prompt(
                question=question,
                context=context,
                additional_facts=facts,
                intent=intent,
                requires_calculation=requires_calculation,
            )
        
        response = self.client.responses.create(
            model=self.model,
            instructions=CLARIFICATION_SYSTEM_PROMPT,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "clarification_result",
                    "strict": True,
                    "schema": CLARIFICATION_SCHEMA,
                }
            },
        )
    
        if not response.output_text:
            raise RuntimeError(
                "추가정보 판정 결과가 비어 있습니다."
            )
    
        result = ClarificationResult.model_validate_json(
            response.output_text
        )
    
        if result.needs_clarification:
            effective_facts = dict(facts)

            for known_fact in result.known_facts:
                current_value = effective_facts.get(
                    known_fact.key
                )
                if (
                    known_fact.key not in effective_facts
                    or is_unknown_value(current_value)
                ):
                    effective_facts[
                        known_fact.key
                    ] = known_fact.value

            filtered_questions = []
            seen_keys = set()

            for clarification_question in result.questions:
                if clarification_question.key in seen_keys:
                    continue

                if is_fact_satisfied(
                    clarification_question.key,
                    effective_facts,
                ):
                    continue

                clarification_question.data_type = (
                    CLARIFICATION_FACT_DATA_TYPES[
                        clarification_question.key
                    ]
                )
                filtered_questions.append(
                    clarification_question
                )
                seen_keys.add(clarification_question.key)

                if len(filtered_questions) == 3:
                    break

            result.questions = filtered_questions
            result.needs_clarification = bool(
                filtered_questions
            )
    
        return result
        
