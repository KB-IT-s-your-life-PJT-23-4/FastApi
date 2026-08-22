import re
from dataclasses import dataclass

from openai import OpenAI

from app.prompts.answer import (
    FINAL_ANSWER_SCHEMA,
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt
)
from app.schemas.answer import AnswerSection, StructuredAnswer


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


def format_won(amount: int) -> str:
    formatted = f"{amount:,}원"
    if amount and amount % 10_000 == 0:
        formatted += f" ({amount // 10_000:,}만원)"
    return formatted


def build_server_calculated_answer(
    calculation: dict,
    *,
    sources: list[str] | None = None,
    recipient_name: str | None = None,
) -> StructuredAnswer:
    """LLM이 서버 계산 결과의 숫자를 변경하지 못하게 답변을 확정한다."""
    gift_amount = int(calculation["gift_amount"])
    previous_gift_amount = int(calculation["previous_gift_amount"])
    total_gift_amount = int(calculation["total_gift_amount"])
    applied_deduction = int(calculation["applied_deduction"])
    taxable_base = int(calculation["taxable_base"])
    tax_rate_percent = int(calculation["tax_rate_percent"])
    progressive_deduction = int(calculation["progressive_deduction"])
    combined_calculated_tax = int(
        calculation["combined_calculated_tax"]
    )
    previous_taxable_base = int(calculation["previous_taxable_base"])
    previous_tax_rate_percent = int(
        calculation["previous_tax_rate_percent"]
    )
    previous_progressive_deduction = int(
        calculation["previous_progressive_deduction"]
    )
    prior_gift_tax_credit = int(calculation["prior_gift_tax_credit"])
    estimated_calculated_tax = int(
        calculation["estimated_calculated_tax"]
    )

    subject = (
        f"{recipient_name}에게 증여할 경우"
        if recipient_name
        else "이번 증여의 경우"
    )
    calculation_items = [
        "합산 증여금액: "
        f"현재 {format_won(gift_amount)} + "
        f"과거 {format_won(previous_gift_amount)} = "
        f"{format_won(total_gift_amount)}",
        "과세표준: "
        f"{format_won(total_gift_amount)} - "
        f"공제액 {format_won(applied_deduction)} = "
        f"{format_won(taxable_base)}",
        "합산 산출세액: "
        f"{format_won(taxable_base)} × {tax_rate_percent}% - "
        f"누진공제액 {format_won(progressive_deduction)} = "
        f"{format_won(combined_calculated_tax)}",
    ]
    if previous_gift_amount > 0:
        calculation_items.extend([
            "과거 증여분 산출세액: "
            f"과거 과세표준 {format_won(previous_taxable_base)} × "
            f"{previous_tax_rate_percent}% - 누진공제액 "
            f"{format_won(previous_progressive_deduction)} = "
            f"{format_won(prior_gift_tax_credit)}",
            "이번 증여 간이 세액: "
            f"{format_won(combined_calculated_tax)} - "
            f"기납부세액공제 {format_won(prior_gift_tax_credit)} = "
            f"{format_won(estimated_calculated_tax)}",
        ])

    return StructuredAnswer(
        summary=(
            f"{subject}, 이번 증여분 예상 증여세는 약 "
            f"{format_won(estimated_calculated_tax)}입니다."
        ),
        sections=[
            AnswerSection(
                title="예상 결과",
                items=[
                    "이번 증여분 예상 증여세: "
                    f"{format_won(estimated_calculated_tax)}"
                ],
            ),
            AnswerSection(
                title="계산 과정",
                items=calculation_items,
            ),
        ],
        sources=sources or [],
        notice=(
            "간이 추정 결과이며 신고세액공제, 세대생략 할증, "
            "재산평가 등에 따라 최종 세액이 달라질 수 있습니다."
        ),
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
        calculation = facts.get("tax_calculation")
        if isinstance(calculation, dict):
            recipient_name = facts.get("recipient_name")
            structured_answer = build_server_calculated_answer(
                calculation,
                sources=structured_answer.sources,
                recipient_name=(
                    recipient_name
                    if isinstance(recipient_name, str)
                    else None
                ),
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
        
