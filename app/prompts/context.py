from __future__ import annotations

import json
from typing import Any


def build_family_context(
    family_data: dict[str, Any] | None,
) -> str:
    if not family_data:
        return ""

    return f"""
[등록 가족 정보]
다음 정보는 Spring 서버 또는 데이터베이스에서 조회한 정보입니다.
사용자에게 같은 정보를 다시 질문하지 마세요.

{json.dumps(
    family_data,
    ensure_ascii=False,
    indent=2,
)}
""".strip()


def build_product_context(
    product_data: dict[str, Any] | None,
) -> str:
    if not product_data:
        return ""

    return f"""
[등록 금융상품 정보]
다음 정보는 Spring 서버 또는 데이터베이스에서 조회한 정보입니다.

제공되지 않은 상품 조건, 금리, 수익률 또는 위험도를
임의로 생성하지 마세요.

{json.dumps(
    product_data,
    ensure_ascii=False,
    indent=2,
)}
""".strip()


def build_calculation_failure_context(
    missing_facts: list[str],
) -> str:
    return f"""
[간이 계산 상태]
간이 계산에 필요한 서버 정보가 부족하여 세액을 계산하지 못했습니다.

부족한 항목:
{json.dumps(
    missing_facts,
    ensure_ascii=False,
    indent=2,
)}

답변 규칙:
- 세액을 임의로 계산하지 마세요.
- 계산하지 못한 이유를 설명하세요.
- 확인된 사실과 관련 법령을 기준으로 일반적인 원칙만 설명하세요.
""".strip()


def build_calculation_error_context() -> str:
    return """
[간이 계산 상태]
입력값 변환 또는 계산 처리에 실패했습니다.

답변 규칙:
- 세액을 임의로 추정하지 마세요.
- 일반적인 세액 계산 구조만 설명하세요.
""".strip()


def combine_contexts(
    *contexts: str,
) -> str:
    return "\n\n".join(
        context.strip()
        for context in contexts
        if context and context.strip()
    )