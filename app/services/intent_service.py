import re

from openai import OpenAI

from app.prompts.intent import(
    QUESTION_INTENT_SCHEMA,
    QUESTION_INTENT_SYSTEM_PROMPT,
    build_question_intent_prompt
)
from app.schemas.chat import QuestionIntentResult
from app.services.fact_normalization_service import (
    extract_calculation_facts_from_question,
)

class IntentService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    def classify(
        self,
        question: str,
        family_names: list[str] | None = None,
    ) -> QuestionIntentResult:
        prompt = build_question_intent_prompt(
            question,
            family_names=family_names,
        )

        response = self.client.responses.create(
            model=self.model,
            instructions=QUESTION_INTENT_SYSTEM_PROMPT,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "question_intent",
                    "strict": True,
                    "schema": QUESTION_INTENT_SCHEMA,
                }
            },
        )

        if not response.output_text:
            raise RuntimeError("질문 유형 판정 결과가 비어 있습니다.")

        result = QuestionIntentResult.model_validate_json(
            response.output_text
        )

        matched_family_name = find_matching_family_name(
            question,
            family_names or [],
        )
        if (
            matched_family_name is not None
            and result.intent in {"assessment", "other_gift"}
        ):
            result.intent = "family"
            result.reason = (
                f"질문에서 등록 가족 '{matched_family_name}'을 "
                "식별했습니다."
            )

        if result.intent in {"family", "assessment"}:
            result.extracted_facts = (
                extract_calculation_facts_from_question(
                    question
                )
            )
        return result


def find_matching_family_name(
    question: str,
    family_names: list[str],
) -> str | None:
    """질문에서 유일하게 식별되는 등록 가족 이름을 반환한다."""
    normalized_question = re.sub(r"\s+", "", question)
    normalized_names = [
        (name, re.sub(r"\s+", "", name))
        for name in family_names
        if name and name.strip()
    ]

    full_name_matches = [
        original_name
        for original_name, normalized_name in normalized_names
        if normalized_name in normalized_question
    ]
    if len(full_name_matches) == 1:
        return full_name_matches[0]
    if full_name_matches:
        return None

    given_name_matches = [
        original_name
        for original_name, normalized_name in normalized_names
        if (
            re.fullmatch(r"[가-힣]{3,}", normalized_name)
            and normalized_name[-2:] in normalized_question
        )
    ]
    if len(given_name_matches) == 1:
        return given_name_matches[0]

    return None
