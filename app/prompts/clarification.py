from __future__ import annotations

import json
from typing import Any


CLARIFICATION_SYSTEM_PROMPT = """
당신은 대한민국 증여세 상담을 위한 사전 정보 확인 AI입니다.

사용자의 질문과 참고 문서를 검토하여
정확한 답변을 위해 추가로 확인해야 하는 사실관계를 판단하세요.

규칙:
1. assessment 또는 family 질문에만 추가 질문을 생성하세요.
2. concept, procedure, product, other_gift 질문에는
   추가 질문을 생성하지 마세요.
3. 사용자가 이미 제공했거나 서버 데이터에 있는 정보는 다시 묻지 마세요.
4. 한 번에 최대 3개까지만 질문하세요.
5. 계산이 필요한 경우 다음 항목을 우선 확인하세요.
   - 증여금액
   - 증여자와 수증자의 관계
   - 수증자의 미성년 여부
   - 최근 10년 내 이전 증여 여부
6. 이전 증여가 있다고 확인된 경우에만 다음을 확인하세요.
   - 이전 증여금액
   - 이전 증여일
   - 현재 증여자와 동일한 증여자인지
7. 이전 증여가 없다면 과거 증여 관련 질문을 생성하지 마세요.
8. 국내 거주자와 최신 세율 사용이 기본값이면 다시 묻지 마세요.
9. 수증자의 일반적인 소득 여부는 묻지 마세요.
10. key는 JSON Schema에 정의된 값만 사용하세요.
11. 최초 질문에 금액이 있으면 gift_amount의 known_facts로 추출하고
    증여금액을 다시 확인하는 질문을 만들지 마세요.
12. "6,000만 원", "6000만원"은 gift_amount 값 "6000만원"으로
    보존하세요. "맞음", "예" 같은 확인값으로 바꾸지 마세요.
13. "22세", "성년 자녀"처럼 나이 또는 성년 여부가 있으면
    known_facts로 추출하고 미성년 여부를 다시 묻지 마세요.
14. 추가 질문은 "맞나요?" 같은 확인형 질문이 아니라 필요한 실제 값을
    직접 입력받는 형태로 작성하세요.
15. 등록 가족 목록이 있으면 질문에 포함된 이름과 정확히 일치하는 가족
    한 명의 정보만 사용하세요.
16. 서로 다른 가족의 사실을 합치지 마세요.
17. 질문에 이름이 없거나 이름만으로 한 명을 특정할 수 없으면
    recipient_name으로 대상 가족의 이름을 질문하세요.
18. 대상 가족을 특정했다면 그 가족의 계산 관련 정보를 known_facts에
    포함하고 이미 제공된 정보는 다시 묻지 마세요.
""".strip()


CLARIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_clarification": {
            "type": "boolean",
        },
        "questions": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": [
                            "recipient_name",
                            "gift_amount",
                            "relationship_type",
                            "recipient_age",
                            "recipient_is_minor",
                            "gift_date",
                            "has_previous_gifts",
                            "previous_gift_amount",
                            "previous_gift_date",
                            "previous_gift_same_donor",
                        ],
                    },
                    "question": {
                        "type": "string",
                    },
                    "reason": {
                        "type": "string",
                    },
                    "required": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "key",
                    "question",
                    "reason",
                    "required",
                ],
                "additionalProperties": False,
            },
        },
        "known_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": [
                            "recipient_name",
                            "gift_amount",
                            "relationship_type",
                            "recipient_age",
                            "recipient_is_minor",
                            "gift_date",
                            "has_previous_gifts",
                            "previous_gift_amount",
                            "previous_gift_date",
                            "previous_gift_same_donor",
                        ],
                    },
                    "value": {
                        "type": "string",
                    },
                },
                "required": [
                    "key",
                    "value",
                ],
                "additionalProperties": False,
            },
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "needs_clarification",
        "questions",
        "known_facts",
        "reason",
    ],
    "additionalProperties": False,
}


def build_clarification_prompt(
    *,
    question: str,
    context: str,
    additional_facts: dict[str, Any],
    intent: str,
    requires_calculation: bool,
) -> str:
    return f"""
[질문 유형]
{intent}

[간이 계산 필요 여부]
{requires_calculation}

[사용자의 최초 질문]
{question}

[확인되었거나 서버에서 제공된 사실]
{json.dumps(
    additional_facts,
    ensure_ascii=False,
    indent=2,
)}

[검색된 참고 문서]
{context}

추가 확인이 필요한 사실관계가 있는지 판단하세요.

세부 규칙:
- assessment 또는 family 질문에서만 추가 질문을 생성하세요.
- requires_calculation이 true이면 계산 필수값을 확인하세요.
- has_previous_gifts가 없거나 확인되지 않았다면 질문하세요.
- has_previous_gifts가 false이면 과거 증여 관련 내용을 묻지 마세요.
- 이미 제공된 사실은 다시 묻지 마세요.
- 최초 질문의 금액, 나이, 관계는 known_facts에 원래 값으로 보존하세요.
- 이미 나온 값을 "맞음" 또는 "예"로 재확인하지 마세요.
- 등록 가족 목록이 있으면 질문의 이름과 일치하는 한 명의 정보만 사용하세요.
- 대상 가족을 특정할 수 없을 때만 recipient_name을 질문하세요.
- 서로 다른 가족의 정보를 하나의 계산 사실로 합치지 마세요.
""".strip()
