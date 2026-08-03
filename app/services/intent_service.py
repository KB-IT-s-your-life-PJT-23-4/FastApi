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
        if result.intent in {"family", "assessment"}:
            result.extracted_facts = (
                extract_calculation_facts_from_question(
                    question
                )
            )
        return result
