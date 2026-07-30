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

def build_gift_tax_rule_context(
    *,
    rate_table: list[dict[str, Any]],
    deduction_table: dict[str, int],
) -> str:
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
- parent_to_adult_child: 부모가 성년 자녀에게 증여
- parent_to_minor_child: 부모가 미성년 자녀에게 증여
- child_to_parent: 자녀가 부모에게 증여
- other_relative: 기타 친족
- other: 공제 대상이 아닌 기타 관계

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
- 계산 과정을 단계별로 표시하세요.
- 결과는 확정세액이 아니라 간이 추정액으로 표현하세요.
""".strip()