import re
from dataclasses import dataclass

from openai import OpenAI

from app.prompts.answer import (
    FINAL_ANSWER_SCHEMA,
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt
)
from app.schemas.answer import StructuredAnswer


@dataclass(frozen=True)
class GeneratedAnswer:
    text: str
    sources: list[str]


def strip_markdown(text: str) -> str:
    cleaned = re.sub(
        r"^\s{0,3}#{1,6}\s*",
        "",
        str(text),
        flags=re.MULTILINE,
    )
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(
        r"^\s*[-*+]\s+",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*\d+[.)]\s+",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    return cleaned.strip()


def render_plain_text_answer(
    answer: StructuredAnswer,
) -> str:
    blocks = [strip_markdown(answer.summary)]

    for section in answer.sections:
        section_lines = [strip_markdown(section.title)]
        section_lines.extend(
            f"{index}. {strip_markdown(item)}"
            for index, item in enumerate(section.items, start=1)
            if strip_markdown(item)
        )
        if len(section_lines) > 1:
            blocks.append("\n".join(section_lines))

    if answer.sources:
        source_lines = ["근거"]
        source_lines.extend(
            f"• {strip_markdown(source)}"
            for source in answer.sources
            if strip_markdown(source)
        )
        if len(source_lines) > 1:
            blocks.append("\n".join(source_lines))

    if answer.notice and strip_markdown(answer.notice):
        blocks.append(
            "안내\n"
            f"{strip_markdown(answer.notice)}"
        )

    return "\n\n".join(
        block for block in blocks if block
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
        return self.generate_result(
            question=question,
            context=context,
            facts=facts,
            intent=intent,
        ).text

    def generate_result(
        self,
        *,
        question: str,
        context: str,
        facts: dict,
        intent: str,
    ) -> GeneratedAnswer:
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
            text={
                "format": {
                    "type": "json_schema",
                    "name": "final_answer",
                    "strict": True,
                    "schema": FINAL_ANSWER_SCHEMA,
                }
            },
        )

        if not response.output_text:
            raise RuntimeError("최종 답변이 비어 있습니다.")

        structured_answer = StructuredAnswer.model_validate_json(
            response.output_text
        )
        if intent in {"product", "procedure"}:
            structured_answer = structured_answer.model_copy(
                update={
                    "sources": [],
                }
            )
        answer = render_plain_text_answer(structured_answer)
        if not answer:
            raise RuntimeError("최종 답변이 비어 있습니다.")

        return GeneratedAnswer(
            text=answer,
            sources=[
                strip_markdown(source)
                for source in structured_answer.sources
                if strip_markdown(source)
            ],
        )
        
