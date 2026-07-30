from __future__ import annotations

import json
from typing import Any


FINAL_ANSWER_SYSTEM_PROMPT = """
당신은 대한민국 증여세 상담을 보조하는 AI입니다.

제공된 참고 문서와 사용자가 확인한 사실,
서버에서 제공된 데이터만을 기반으로 답변하세요.

규칙:
1. 참고 문서나 서버 데이터에 없는 내용을 임의로 생성하지 마세요.
2. 사용자가 제공한 사실과 서버 제공 정보를 구분하세요.
3. 답변 근거가 되는 법령과 법령해석을 제시하세요.
4. 확인되지 않은 정보는 추측하지 마세요.
5. 법률, 공제액, 세율 및 행정해석은 개정될 수 있음을 안내하세요.
6. 사용자가 이해하기 쉬운 한국어로 설명하세요.
7. 이미 확인된 사실을 다시 질문하지 마세요.
8. 서버 간이 세액 계산 결과가 있으면 그 결과를 사용하세요.
9. 서버가 계산한 세액을 다시 계산하거나 변경하지 마세요.
10. 세액은 확정액이 아니라 간이 추정액으로 표현하세요.
11. 등록 상품 데이터에 없는 수익률, 금리 또는 위험도를 만들지 마세요.
12. family 질문에서는 서버가 제공한 가족 정보를 사용하세요.
13. product 질문에서는 서버가 제공한 상품 정보를 사용하세요.
""".strip()


ANSWER_FORMATS: dict[str, str] = {
    "concept": """
1. 용어의 의미
2. 쉽게 설명한 예시
3. 관련 법령 근거
4. 주의사항 및 개정 가능성
""".strip(),

    "family": """
1. 등록 가족 기준 핵심 답변
2. 적용한 가족 정보
3. 계산 또는 판단 과정
4. 관련 법령 및 법령해석
5. 주의사항
""".strip(),

    "assessment": """
1. 결론 또는 간이 계산 결과
2. 계산 또는 판단 과정
3. 적용한 공제와 세율
4. 법령 및 법령해석 근거
5. 주의사항 및 개정 가능성
""".strip(),

    "procedure": """
1. 핵심 답변
2. 신고 또는 납부 절차
3. 기한 및 준비사항
4. 관련 법령 근거
5. 주의사항 및 개정 가능성
""".strip(),

    "product": """
1. 상품 개요
2. 주요 특징
3. 수익성과 위험 요인
4. 증여 목적에서 고려할 점
5. 데이터 기준일 및 주의사항
""".strip(),

    "other_gift": """
1. 결론
2. 판단 근거
3. 관련 법령 및 법령해석
4. 주의사항 및 개정 가능성
""".strip(),
}


def build_final_answer_prompt(
    *,
    question: str,
    context: str,
    additional_facts: dict[str, Any],
    intent: str,
) -> str:
    answer_format = ANSWER_FORMATS.get(
        intent,
        ANSWER_FORMATS["other_gift"],
    )

    return f"""
[질문 유형]
{intent}

[사용자의 질문]
{question}

[확인된 사실 및 서버 제공 정보]
{json.dumps(
    additional_facts,
    ensure_ascii=False,
    indent=2,
)}

[참고 자료]
{context}

[답변 형식]
{answer_format}
""".strip()