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


def build_families_context(
    families_data: list[dict[str, Any]] | None,
) -> str:
    if not families_data:
        return ""

    return f"""
[등록 가족 목록]
다음 정보는 Spring 서버 또는 데이터베이스에서 조회한 정보입니다.

질문에 가족의 전체 이름 또는 성을 생략한 이름이 포함되어 있으면 유일하게
일치하는 가족 한 명의 정보만 사용하세요. 예를 들어 등록 이름이 "김민지"이고
질문에 "민지"가 있으면 김민지의 정보를 사용하세요. 서로 다른 가족의 관계,
나이, 증여금액 또는 과거 증여 정보를 합치지 마세요.

이름이 없거나 같은 이름이 여러 명이어서 대상을 특정할 수 없다면
추측하지 말고 대상 가족의 이름을 확인하세요.

{json.dumps(
    families_data,
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


def build_gift_tax_calculation_context(
    calculation: dict[str, int | bool],
) -> str:
    return f"""
[서버 계산 완료 결과]
다음 값은 서버가 원 단위 정수로 정규화한 뒤 세율표를 적용해 계산한 결과입니다.
LLM이 금액, 공제액, 과세표준, 세율 또는 산출세액을 다시 계산하거나 변경하지 마세요.

{json.dumps(
    calculation,
    ensure_ascii=False,
    indent=2,
)}

답변 계산식:
- 합산 증여금액 = 현재 증여금액 + 과거 합산 증여금액
- 과세표준 = 합산 증여금액 - 적용 공제액
- 합산 산출세액 = 과세표준 × 적용 세율 - 누진공제액
- 과거 증여분 산출세액 = 과거 과세표준 × 과거 적용 세율 - 과거 누진공제액
- 이번 증여 간이 세액 = 합산 산출세액 - 과거 증여분 기납부세액공제
- 답변의 결론과 예상 세액에는 combined_calculated_tax가 아니라
  estimated_calculated_tax를 사용하세요.
- 위 서버 계산값을 그대로 설명하고, 결과는 간이 추정액으로 표현하세요.
""".strip()


def combine_contexts(
    *contexts: str,
) -> str:
    return "\n\n".join(
        context.strip()
        for context in contexts
        if context and context.strip()
    )

def build_gift_tax_rule_context(
    *,
    rate_table: list[dict[str, Any]],
    deduction_table: dict[str, int],
    relationship_type: str | None = None,
) -> str:
    selected_deduction = deduction_table.get(
        relationship_type or ""
    )
    selected_deduction_context = ""

    if selected_deduction is not None:
        selected_deduction_context = f"""

[이번 계산에 적용할 증여재산공제]
- 적용 관계 코드: {relationship_type}
- 공제 한도: {selected_deduction:,}원 ({selected_deduction // 10_000:,}만원)
- 위 공제 한도를 그대로 사용하고 숫자를 줄이거나 다른 단위로 바꾸지 마세요.
""".rstrip()

    return f"""
[서버 제공 증여세 간이 계산 기준]

다음 세율표와 증여재산공제표를 사용하여 간이 세액을 계산하세요.

세율표:
{json.dumps(
    rate_table,
    ensure_ascii=False,
    indent=2,
)}

증여재산공제표:
{json.dumps(
    deduction_table,
    ensure_ascii=False,
    indent=2,
)}

관계 코드:
- spouse: 배우자
- parent_to_adult_child: 부모가 성년 자녀에게 증여, 공제 한도 50,000,000원 (5,000만원)
- parent_to_minor_child: 부모가 미성년 자녀에게 증여, 공제 한도 20,000,000원 (2,000만원)
- child_to_parent: 자녀가 부모에게 증여
- other_relative: 기타 친족
- other: 공제 대상이 아닌 기타 관계
{selected_deduction_context}

세율표 사용 방법:
1. 현재 증여금액과 합산 대상 과거 증여금액을 더하세요.
2. 관계에 해당하는 증여재산공제를 차감하세요.
3. 계산된 과세표준이 속하는 세율 구간을 찾으세요.
4. 다음 식으로 간이 산출세액을 계산하세요.

   간이 산출세액
   = 과세표준 × 적용 세율 - 누진공제액

5. 과세표준이 0원 이하라면 간이 산출세액은 0원입니다.
6. upper_limit이 null인 구간은 상한이 없는 마지막 구간입니다.

중요:
- 서버가 제공한 세율과 공제액만 사용하세요.
- 다른 세율이나 공제액을 임의로 적용하지 마세요.
- 성년 자녀 공제는 50,000,000원(5,000만원)이며 5,000,000원(500만원)이 아닙니다.
- 미성년 자녀 공제는 20,000,000원(2,000만원)이며 2,000,000원(200만원)이 아닙니다.
- 공제액은 원 단위 정수와 괄호 안의 만원 단위가 일치하는지 확인하세요.
- 계산 과정을 단계별로 표시하세요.
- 결과는 확정세액이 아니라 간이 추정액으로 표현하세요.
""".strip()
