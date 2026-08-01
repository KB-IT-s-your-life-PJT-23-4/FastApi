from openai import OpenAI

from app.prompts.answer import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt
)

class AnswerService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    def generate(
        self,
        *,
        question: str,
        context: str,
        facts: dict,
        intent: str,
    ) -> str:
        prompt = build_final_answer_prompt(
            question=question,
            context=context,
            additional_facts=facts,
            intent=intent,
        )

        response = self.client.responses.create(
            model = self.model,
            instructions = FINAL_ANSWER_SYSTEM_PROMPT,
            input=prompt,
        )

        answer = response.output_text.strip()

        if not answer:
            raise RuntimeError("최종 답변이 비어 있습니다.")

        return answer
        
