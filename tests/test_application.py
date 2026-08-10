from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import dependencies
from app.collectors import law_article_cosine_collector
from app.collectors import nts_interpretation_cosine_collector
from app.collectors.nts_interpretation_collector import (
    find_interpretation_chunk_ids_before,
    is_interpretation_on_or_after,
    parse_interpretation_date,
)
from app.core.constants import RAG_INTENTS
from app.data.gift_tax_rules import (
    GIFT_DEDUCTION_TABLE,
    GIFT_TAX_RATE_TABLE,
)
from app.main import app
from app.prompts.answer import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt,
)
from app.prompts.context import build_gift_tax_rule_context
from app.prompts.context import build_families_context
from app.repositories.interpretation_repository import (
    InterpretationRepository,
)
from app.services.context_service import ContextService
from app.services.fact_normalization_service import (
    extract_calculation_facts_from_question,
    normalize_calculation_facts,
    parse_korean_amount,
)
from app.services.gift_tax_service import (
    apply_gift_tax_rate,
    calculate_simple_gift_tax,
)
from app.services.retrieval_service import (
    RetrievalService,
    group_law_results_by_article,
)
from app.services.intent_service import (
    IntentService,
    find_matching_family_name,
)
from app.services.clarification_service import ClarificationService
from app.prompts.intent import build_question_intent_prompt
from app.schemas.chat import (
    ChatRequest,
    ClarificationResult,
    KnownFact,
    QuestionIntentResult,
)
from app.schemas.answer import AnswerSection, StructuredAnswer
from app.services.answer_service import (
    AnswerService,
    render_plain_text_answer,
)
from app.services.chat_service import ChatService, merge_known_facts


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_chat_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/clarification" in paths


def test_chat_requests_use_families_instead_of_family() -> None:
    schemas = app.openapi()["components"]["schemas"]

    for schema_name in ["ChatRequest", "ClarificationRequest"]:
        properties = schemas[schema_name]["properties"]
        assert "families" in properties
        assert "family" not in properties


def test_chat_request_rejects_legacy_family_field() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            question="김민수에게 증여하면 세금이 얼마인가요?",
            family={
                "family_id": 1,
                "name": "김민수",
                "relationship_type": "parent_to_adult_child",
            },
        )


def test_chat_request_accepts_up_to_three_families() -> None:
    family = {
        "family_id": 1,
        "name": "김민수",
        "relationship_type": "parent_to_adult_child",
        "recipient_age": 30,
        "gift_amount": 60_000_000,
    }

    request = ChatRequest(
        question="김민수에게 증여하면 세금이 얼마인가요?",
        families=[
            {**family, "family_id": family_id}
            for family_id in range(1, 4)
        ],
    )

    assert len(request.families) == 3


def test_chat_request_rejects_more_than_three_families() -> None:
    family = {
        "name": "김민수",
        "relationship_type": "parent_to_adult_child",
    }

    with pytest.raises(ValidationError):
        ChatRequest(
            question="증여세를 계산해 주세요.",
            families=[
                {**family, "family_id": family_id}
                for family_id in range(1, 5)
            ],
        )


def test_families_context_requires_name_based_selection() -> None:
    context = build_families_context([
        {
            "family_id": 1,
            "name": "김민수",
            "relationship_type": "parent_to_adult_child",
        },
        {
            "family_id": 2,
            "name": "김민지",
            "relationship_type": "parent_to_adult_child",
        },
    ])

    assert "김민수" in context
    assert "김민지" in context
    assert "일치하는 가족 한 명의 정보만" in context
    assert "서로 다른 가족" in context


def test_intent_prompt_receives_registered_family_names() -> None:
    prompt = build_question_intent_prompt(
        "김민수에게 증여하면 세금이 얼마인가요?",
        family_names=["김민수", "김민지"],
    )

    assert "[등록 가족 이름]" in prompt
    assert "김민수" in prompt
    assert "김민지" in prompt


def test_given_name_matches_unique_registered_family() -> None:
    matched = find_matching_family_name(
        "민지에게 2000만원 증여하면 증여세가 얼마나 나오나요?",
        ["김민수", "김민지"],
    )

    assert matched == "김민지"


def test_ambiguous_given_name_does_not_select_family() -> None:
    matched = find_matching_family_name(
        "민지에게 증여하려고 합니다.",
        ["김민지", "박민지"],
    )

    assert matched is None


def test_assessment_is_overridden_when_family_name_matches() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"intent":"assessment",'
            '"requires_calculation":true,'
            '"reason":"일반 계산 질문"}'
        )
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: response
        )
    )
    service = IntentService(
        client=client,
        model="test-model",
    )

    result = service.classify(
        "민지에게 2000만원 증여하면 증여세가 얼마나 나오나요?",
        family_names=["김민수", "김민지"],
    )

    assert result.intent == "family"
    assert "김민지" in result.reason
    assert result.requires_calculation is True


def test_selected_family_facts_are_used_before_clarification() -> None:
    captured: dict = {}

    class FakeIntentService:
        def classify(self, question, family_names):
            return QuestionIntentResult(
                intent="family",
                requires_calculation=True,
                extracted_facts={"gift_amount": 20_000_000},
            )

    class FakeClarificationService:
        def analyze(self, **kwargs):
            captured.update(kwargs)
            return ClarificationResult(
                needs_clarification=False,
                questions=[],
                known_facts=[],
                reason="필수 정보가 모두 있습니다.",
            )

    service = ChatService(
        intent_service=FakeIntentService(),
        retrieval_service=SimpleNamespace(
            retrieve=lambda question: ""
        ),
        clarification_service=FakeClarificationService(),
        answer_service=SimpleNamespace(
            generate=lambda **kwargs: "예상 세액 답변"
        ),
        context_service=ContextService(),
    )

    service.process(ChatRequest(
        question="민지에게 2000만원을 증여하면 얼마인가요?",
        families=[
            {
                "family_id": 1,
                "name": "김민수",
                "relationship_type": "parent_to_adult_child",
                "recipient_age": 30,
                "recipient_is_minor": False,
                "has_previous_gifts": False,
            },
            {
                "family_id": 2,
                "name": "김민지",
                "relationship_type": "parent_to_adult_child",
                "gift_amount": 30_000_000,
                "recipient_age": 25,
                "recipient_is_minor": False,
                "has_previous_gifts": True,
                "previous_gift_amount": 10_000_000,
                "previous_gift_date": "2023-05-01",
                "previous_gift_same_donor": True,
                "previously_used_deduction": 10_000_000,
            },
        ],
    ))

    facts = captured["facts"]
    assert facts["recipient_name"] == "김민지"
    assert facts["gift_amount"] == 20_000_000
    assert facts["relationship_type"] == "parent_to_adult_child"
    assert facts["recipient_age"] == 25
    assert facts["recipient_is_minor"] is False
    assert facts["has_previous_gifts"] is True
    assert facts["previous_gift_amount"] == 10_000_000


def test_clarification_question_data_type_is_corrected_by_key() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":[{'
            '"key":"has_previous_gifts",'
            '"data_type":"string",'
            '"question":"이전 증여가 있었나요?",'
            '"reason":"합산 여부 확인",'
            '"required":true}],'
            '"known_facts":[],'
            '"reason":"이전 증여 여부가 필요합니다."}'
        )
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: response
        )
    )
    service = ClarificationService(
        client=client,
        model="test-model",
    )

    result = service.analyze(
        question="증여세를 계산해 주세요.",
        context="",
        facts={},
        intent="assessment",
        requires_calculation=True,
    )

    assert result.questions[0].data_type == "boolean"


def test_clarification_question_schema_exposes_data_type() -> None:
    schema = app.openapi()["components"]["schemas"][
        "ClarificationQuestion"
    ]

    assert "data_type" in schema["properties"]
    assert "data_type" in schema["required"]


def test_known_false_and_zero_facts_are_not_asked_again() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":['
            '{"key":"has_previous_gifts",'
            '"data_type":"boolean",'
            '"question":"이전 증여가 있었나요?",'
            '"reason":"합산 여부 확인","required":true},'
            '{"key":"previous_gift_amount",'
            '"data_type":"integer",'
            '"question":"이전 증여금액은 얼마인가요?",'
            '"reason":"합산 금액 확인","required":true},'
            '{"key":"previous_gift_date",'
            '"data_type":"date",'
            '"question":"이전 증여일은 언제인가요?",'
            '"reason":"합산 기간 확인","required":true},'
            '{"key":"previous_gift_same_donor",'
            '"data_type":"boolean",'
            '"question":"동일한 증여자인가요?",'
            '"reason":"합산 대상 확인","required":true}],'
            '"known_facts":[],'
            '"reason":"추가 정보가 필요합니다."}'
        )
    )
    service = ClarificationService(
        client=SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: response
            )
        ),
        model="test-model",
    )

    result = service.analyze(
        question="성인 자녀에게 증여하려고 합니다.",
        context="",
        facts={
            "has_previous_gifts": False,
            "previous_gift_amount": 0,
            "previous_gift_date": "",
            "previous_gift_same_donor": False,
        },
        intent="assessment",
        requires_calculation=True,
    )

    assert result.needs_clarification is False
    assert result.questions == []


def test_duplicate_clarification_keys_are_removed() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":['
            '{"key":"has_previous_gifts",'
            '"data_type":"string",'
            '"question":"이전 증여가 있었나요?",'
            '"reason":"합산 여부 확인","required":true},'
            '{"key":"has_previous_gifts",'
            '"data_type":"string",'
            '"question":"과거 증여 여부를 알려주세요.",'
            '"reason":"합산 여부 확인","required":true}],'
            '"known_facts":[],'
            '"reason":"이전 증여 여부가 필요합니다."}'
        )
    )
    service = ClarificationService(
        client=SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: response
            )
        ),
        model="test-model",
    )

    result = service.analyze(
        question="증여세를 계산해 주세요.",
        context="",
        facts={},
        intent="assessment",
        requires_calculation=True,
    )

    assert len(result.questions) == 1
    assert result.questions[0].key == "has_previous_gifts"
    assert result.questions[0].data_type == "boolean"


def test_clarification_questions_prioritize_age_and_previous_gifts() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":['
            '{"key":"gift_amount","data_type":"integer",'
            '"question":"증여금액은 얼마인가요?",'
            '"reason":"계산 금액 확인","required":true},'
            '{"key":"relationship_type","data_type":"string",'
            '"question":"관계는 무엇인가요?",'
            '"reason":"공제 확인","required":true},'
            '{"key":"previous_gift_amount","data_type":"integer",'
            '"question":"이전 증여금액은 얼마인가요?",'
            '"reason":"합산 금액 확인","required":true},'
            '{"key":"recipient_age","data_type":"integer",'
            '"question":"수증자의 나이는 몇 살인가요?",'
            '"reason":"공제 확인","required":true},'
            '{"key":"previous_gift_date","data_type":"date",'
            '"question":"이전 증여일은 언제인가요?",'
            '"reason":"합산 기간 확인","required":true}],'
            '"known_facts":[],'
            '"reason":"추가 정보가 필요합니다."}'
        )
    )
    service = ClarificationService(
        client=SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: response
            )
        ),
        model="test-model",
    )

    result = service.analyze(
        question="증여세를 계산해 주세요.",
        context="",
        facts={"has_previous_gifts": True},
        intent="assessment",
        requires_calculation=True,
    )

    assert [question.key for question in result.questions] == [
        "recipient_age",
        "previous_gift_amount",
        "previous_gift_date",
    ]


def test_previous_gift_details_wait_for_previous_gift_confirmation() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":['
            '{"key":"previous_gift_amount","data_type":"integer",'
            '"question":"이전 증여금액은 얼마인가요?",'
            '"reason":"합산 금액 확인","required":true},'
            '{"key":"has_previous_gifts","data_type":"boolean",'
            '"question":"이전 증여가 있었나요?",'
            '"reason":"합산 여부 확인","required":true},'
            '{"key":"recipient_age","data_type":"integer",'
            '"question":"수증자의 나이는 몇 살인가요?",'
            '"reason":"공제 확인","required":true}],'
            '"known_facts":[],'
            '"reason":"추가 정보가 필요합니다."}'
        )
    )
    service = ClarificationService(
        client=SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: response
            )
        ),
        model="test-model",
    )

    result = service.analyze(
        question="증여세를 계산해 주세요.",
        context="",
        facts={},
        intent="assessment",
        requires_calculation=True,
    )

    assert [question.key for question in result.questions] == [
        "recipient_age",
        "has_previous_gifts",
    ]


def test_known_fact_replaces_unknown_but_not_valid_false() -> None:
    facts = {
        "gift_amount": None,
        "has_previous_gifts": False,
    }

    merge_known_facts(
        facts,
        [
            KnownFact(key="gift_amount", value="6000만원"),
            KnownFact(key="has_previous_gifts", value="true"),
        ],
    )

    assert facts["gift_amount"] == "6000만원"
    assert facts["has_previous_gifts"] is False


def test_known_fact_from_same_llm_response_removes_question() -> None:
    response = SimpleNamespace(
        output_text=(
            '{"needs_clarification":true,'
            '"questions":[{'
            '"key":"gift_amount",'
            '"data_type":"integer",'
            '"question":"증여금액은 얼마인가요?",'
            '"reason":"세액 계산에 필요",'
            '"required":true}],'
            '"known_facts":[{'
            '"key":"gift_amount",'
            '"value":"6000만원"}],'
            '"reason":"금액을 확인했습니다."}'
        )
    )
    service = ClarificationService(
        client=SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: response
            )
        ),
        model="test-model",
    )

    result = service.analyze(
        question="6000만원을 증여하려고 합니다.",
        context="",
        facts={"gift_amount": None},
        intent="assessment",
        requires_calculation=True,
    )

    assert result.needs_clarification is False
    assert result.questions == []


def test_openai_clients_use_separate_api_keys(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

    settings = SimpleNamespace(
        openai_api_key="chat-api-key",
        openai_embedding_api_key="embedding-api-key",
    )

    dependencies.get_openai_client.cache_clear()
    dependencies.get_openai_embedding_client.cache_clear()
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        dependencies,
        "OpenAI",
        FakeOpenAI,
    )

    try:
        chat_client = dependencies.get_openai_client()
        embedding_client = (
            dependencies.get_openai_embedding_client()
        )

        assert chat_client.api_key == "chat-api-key"
        assert embedding_client.api_key == "embedding-api-key"
    finally:
        dependencies.get_openai_client.cache_clear()
        dependencies.get_openai_embedding_client.cache_clear()


def test_answer_prompt_uses_conversational_style() -> None:
    prompt = build_final_answer_prompt(
        question="증여세가 무엇인가요?",
        context="상속세 및 증여세법 제2조",
        additional_facts={},
        intent="concept",
    )

    assert "첫 문장에서 사용자의 질문에 바로 답하세요" in (
        FINAL_ANSWER_SYSTEM_PROMPT
    )
    assert "자연스럽고 친절한 존댓말" in (
        FINAL_ANSWER_SYSTEM_PROMPT
    )
    assert "문서 전문, 청크 ID, 검색 거리" in prompt
    assert "필요한 경우에만 짧은 예시" in prompt


def test_structured_answer_is_rendered_without_markdown() -> None:
    rendered = render_plain_text_answer(
        StructuredAnswer(
            summary="**예상 세액은 10만원입니다.**",
            sections=[
                AnswerSection(
                    title="### 계산 과정",
                    items=[
                        "**증여금액**: 6,000만원",
                        "과세표준 × 10% = 10만원",
                    ],
                )
            ],
            sources=["**상속세 및 증여세법** 제55조"],
            notice="`간이 추정액`입니다.",
        )
    )

    assert "###" not in rendered
    assert "**" not in rendered
    assert "`" not in rendered
    assert "계산 과정" in rendered
    assert "1. 증여금액: 6,000만원" in rendered
    assert "근거" in rendered
    assert "안내" in rendered


def test_answer_service_uses_structured_output() -> None:
    captured: dict = {}

    def create_response(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_text=(
                '{"summary":"예상 세액은 10만원입니다.",'
                '"sections":[],"sources":[],'
                '"notice":"간이 추정액입니다."}'
            )
        )

    service = AnswerService(
        client=SimpleNamespace(
            responses=SimpleNamespace(create=create_response)
        ),
        model="test-model",
    )

    answer = service.generate(
        question="증여세가 얼마인가요?",
        context="참고 자료",
        facts={},
        intent="assessment",
    )

    assert captured["text"]["format"]["type"] == "json_schema"
    assert answer == (
        "예상 세액은 10만원입니다.\n\n"
        "안내\n간이 추정액입니다."
    )


@pytest.mark.parametrize(
    "intent",
    ["product", "procedure"],
)
def test_answer_service_removes_sources_for_non_legal_intents(
    intent,
) -> None:
    def create_response(**kwargs):
        return SimpleNamespace(
            output_text=(
                '{"summary":"안내 답변입니다.",'
                '"sections":[],"sources":'
                '["상속세 및 증여세법 제1조"],'
                '"notice":null}'
            )
        )

    service = AnswerService(
        client=SimpleNamespace(
            responses=SimpleNamespace(create=create_response)
        ),
        model="test-model",
    )

    answer = service.generate(
        question="안내해 주세요.",
        context="참고 자료",
        facts={},
        intent=intent,
    )

    assert answer == "안내 답변입니다."
    assert "근거" not in answer
    assert "제1조" not in answer


def test_question_facts_override_confirmation_answers() -> None:
    question = (
        "부모가 22세 성년 자녀에게 "
        "6000만원을 증여하면 세금이 얼마인가요?"
    )
    extracted = extract_calculation_facts_from_question(
        question
    )
    facts = normalize_calculation_facts(
        {
            "gift_amount": "맞음",
            "relationship_type": "부모",
            "recipient_age": "22세",
            "recipient_is_minor": "맞음",
            "has_previous_gifts": False,
        },
        question=question,
    )

    assert extracted["gift_amount"] == 60_000_000
    assert extracted["recipient_is_minor"] is False
    assert facts["gift_amount"] == 60_000_000
    assert facts["recipient_age"] == 22
    assert facts["recipient_is_minor"] is False
    assert facts["relationship_type"] == (
        "parent_to_adult_child"
    )


@pytest.mark.parametrize(
    ("raw_amount", "expected"),
    [
        ("6000만원", 60_000_000),
        ("1억", 100_000_000),
        ("1억원", 100_000_000),
        ("1.5억", 150_000_000),
        ("60,000,000원", 60_000_000),
        (60_000_000, 60_000_000),
    ],
)
def test_korean_amount_is_normalized_to_integer_won(
    raw_amount,
    expected,
) -> None:
    normalized = parse_korean_amount(raw_amount)

    assert normalized == expected
    assert type(normalized) is int


def test_gift_tax_is_calculated_by_server() -> None:
    estimate = calculate_simple_gift_tax(
        gift_amount=60_000_000,
        relationship_type="parent_to_adult_child",
    )

    assert estimate.total_gift_amount == 60_000_000
    assert estimate.applied_deduction == 50_000_000
    assert estimate.taxable_base == 10_000_000
    assert estimate.tax_rate_percent == 10
    assert estimate.progressive_deduction == 0
    assert estimate.estimated_calculated_tax == 1_000_000


def test_previous_gift_uses_full_deduction_once_for_combined_base() -> None:
    estimate = calculate_simple_gift_tax(
        gift_amount=60_000_000,
        relationship_type="parent_to_adult_child",
        previous_gift_amount=15_000_000,
        previously_used_deduction=15_000_000,
    )

    assert estimate.total_gift_amount == 75_000_000
    assert estimate.deduction_limit == 50_000_000
    assert estimate.applied_deduction == 50_000_000
    assert estimate.taxable_base == 25_000_000
    assert estimate.tax_rate_percent == 10
    assert estimate.previous_calculated_tax == 0
    assert estimate.prior_gift_tax_credit == 0
    assert estimate.estimated_calculated_tax == 2_500_000


def test_current_gift_tax_subtracts_previous_gift_tax_credit() -> None:
    estimate = calculate_simple_gift_tax(
        gift_amount=20_000_000,
        relationship_type="parent_to_adult_child",
        previous_gift_amount=230_000_000,
        previously_used_deduction=50_000_000,
    )

    assert estimate.total_gift_amount == 250_000_000
    assert estimate.taxable_base == 200_000_000
    assert estimate.tax_rate_percent == 20
    assert estimate.progressive_deduction == 10_000_000
    assert estimate.combined_calculated_tax == 30_000_000
    assert estimate.previous_taxable_base == 180_000_000
    assert estimate.previous_tax_rate_percent == 20
    assert estimate.previous_progressive_deduction == 10_000_000
    assert estimate.previous_calculated_tax == 26_000_000
    assert estimate.prior_gift_tax_credit == 26_000_000
    assert estimate.estimated_calculated_tax == 4_000_000


def test_current_gift_tax_handles_progressive_bracket_crossing() -> None:
    estimate = calculate_simple_gift_tax(
        gift_amount=20_000_000,
        relationship_type="parent_to_adult_child",
        previous_gift_amount=140_000_000,
        previously_used_deduction=50_000_000,
    )

    # 과거 과세표준 9,000만원: 10% = 900만원
    assert estimate.previous_taxable_base == 90_000_000
    assert estimate.previous_calculated_tax == 9_000_000

    # 합산 과세표준 1억 1,000만원: 20% - 1,000만원 = 1,200만원
    assert estimate.taxable_base == 110_000_000
    assert estimate.combined_calculated_tax == 12_000_000

    # 이번 2,000만원으로 증가한 세액만 반환
    assert estimate.estimated_calculated_tax == 3_000_000


def test_gift_tax_calculation_process_is_logged(caplog) -> None:
    caplog.set_level("INFO", logger="uvicorn.error")

    calculate_simple_gift_tax(
        gift_amount=60_000_000,
        relationship_type="parent_to_adult_child",
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any("gift_tax.calculation_started" in message for message in messages)
    assert any("gift_tax.deduction_applied" in message for message in messages)
    assert any(
        "gift_tax.taxable_base_calculated" in message
        for message in messages
    )
    assert any("gift_tax.rate_selected" in message for message in messages)
    assert any(
        "gift_tax.calculation_completed" in message
        and "estimated_calculated_tax=1000000" in message
        for message in messages
    )


def test_progressive_tax_rate_is_selected_by_taxable_base() -> None:
    rate, progressive_deduction, calculated_tax = apply_gift_tax_rate(
        500_000_000
    )

    assert rate == 20
    assert progressive_deduction == 10_000_000
    assert calculated_tax == 90_000_000


def test_final_context_contains_precalculated_integer_tax_values() -> None:
    context, facts = ContextService().build_final_context(
        base_context="",
        facts={
            "gift_amount": "6000만원",
            "relationship_type": "parent_to_adult_child",
            "has_previous_gifts": False,
            "previously_used_deduction": 0,
        },
        question="성인 아들에게 6000만원을 증여하면 얼마인가요?",
        intent="assessment",
        requires_calculation=True,
    )

    calculation = facts["tax_calculation"]
    assert calculation["gift_amount"] == 60_000_000
    assert type(calculation["gift_amount"]) is int
    assert calculation["tax_rate_percent"] == 10
    assert calculation["estimated_calculated_tax"] == 1_000_000
    assert "[서버 계산 완료 결과]" in context
    assert "LLM이 금액, 공제액, 과세표준, 세율 또는 산출세액을" in context


def test_adult_child_deduction_is_explicit_in_context() -> None:
    context = build_gift_tax_rule_context(
        rate_table=GIFT_TAX_RATE_TABLE,
        deduction_table=GIFT_DEDUCTION_TABLE,
        relationship_type="parent_to_adult_child",
    )

    assert "공제 한도: 50,000,000원 (5,000만원)" in context
    assert "5,000,000원(500만원)이 아닙니다" in context


def test_minor_child_deduction_is_explicit_in_context() -> None:
    context = build_gift_tax_rule_context(
        rate_table=GIFT_TAX_RATE_TABLE,
        deduction_table=GIFT_DEDUCTION_TABLE,
        relationship_type="parent_to_minor_child",
    )

    assert "공제 한도: 20,000,000원 (2,000만원)" in context
    assert "2,000,000원(200만원)이 아닙니다" in context


def test_all_gift_intents_use_rag() -> None:
    assert "product" in RAG_INTENTS
    assert "other_gift" in RAG_INTENTS


def test_multiple_product_contexts_are_combined() -> None:
    product = SimpleNamespace(
        model_dump=lambda mode: {
            "product_id": 1,
            "product_name": "테스트 상품",
        }
    )

    context = ContextService().build_products_context([product])

    assert "선택 상품 1" in context
    assert "테스트 상품" in context


class FakeCollection:
    def __init__(self) -> None:
        self.query_arguments: dict = {}

    def count(self) -> int:
        return 1

    def query(self, **kwargs):
        self.query_arguments = kwargs
        return {
            "ids": [["chunk-1"]],
            "documents": [["검색 문서"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }


class FakeEmbeddings:
    def create(self, **kwargs):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )


def test_repository_queries_with_openai_embedding() -> None:
    collection = FakeCollection()
    repository = InterpretationRepository(
        collection=collection,
        embedding_client=SimpleNamespace(
            embeddings=FakeEmbeddings()
        ),
        embedding_model="test-embedding-model",
    )

    repository.search(question="증여세", top_k=1)

    assert collection.query_arguments["query_embeddings"] == [
        [0.1, 0.2]
    ]
    assert "query_texts" not in collection.query_arguments


class FakeRepository:
    def search(self, **kwargs):
        return {
            "ids": [["chunk-1"]],
            "documents": [["검색 문서"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }


def test_retrieval_formats_both_search_results() -> None:
    service = RetrievalService(
        interpretation_repository=FakeRepository(),
        law_repository=FakeRepository(),
    )

    context = service.retrieve("증여세")

    assert "국세청 법령해석 사례" in context
    assert "법령해석 1" in context
    assert "관련 법령 원문" in context
    assert "법령 원문 1" in context


def test_law_chunks_are_grouped_by_article() -> None:
    search_result = {
        "ids": [["article-2", "article-1", "other"]],
        "documents": [[
            "[내용]\n② 두 번째 항",
            "[내용]\n① 첫 번째 항",
            "[내용]\n다른 조문",
        ]],
        "metadatas": [[
            {
                "law_id": "law-1",
                "article_key": "article-1",
                "law_name": "테스트법",
                "article_label": "제1조",
                "section_index": 2,
                "chunk_index": 0,
                "paragraph_number": "②",
            },
            {
                "law_id": "law-1",
                "article_key": "article-1",
                "law_name": "테스트법",
                "article_label": "제1조",
                "section_index": 1,
                "chunk_index": 0,
                "paragraph_number": "①",
            },
            {
                "law_id": "law-1",
                "article_key": "article-2",
                "law_name": "테스트법",
                "article_label": "제2조",
                "section_index": 0,
                "chunk_index": 0,
                "paragraph_number": "",
            },
        ]],
        "distances": [[0.2, 0.3, 0.4]],
    }

    grouped = group_law_results_by_article(
        search_result,
        max_articles=2,
    )

    assert len(grouped["documents"][0]) == 2
    first_document = grouped["documents"][0][0]
    assert first_document.index("① 첫 번째 항") < (
        first_document.index("② 두 번째 항")
    )
    assert grouped["metadatas"][0][0][
        "grouped_chunk_count"
    ] == 2
    assert grouped["distances"][0][0] == 0.2


def test_cosine_collectors_create_hnsw_cosine_collections(
    monkeypatch,
) -> None:
    calls: list[dict] = []
    sentinel = object()

    class FakeChromaClient:
        def get_or_create_collection(self, **kwargs):
            calls.append(kwargs)
            return sentinel

    fake_client = FakeChromaClient()
    monkeypatch.setattr(
        law_article_cosine_collector,
        "chroma_client",
        fake_client,
    )
    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "chroma_client",
        fake_client,
    )

    assert (
        law_article_cosine_collector.get_cosine_law_collection(
            "law-cosine-test"
        )
        is sentinel
    )
    assert (
        nts_interpretation_cosine_collector.
        get_cosine_interpretation_collection(
            "interpretation-cosine-test"
        )
        is sentinel
    )

    assert [call["name"] for call in calls] == [
        "law-cosine-test",
        "interpretation-cosine-test",
    ]
    assert all(
        call["configuration"]["hnsw"]["space"]
        == "cosine"
        for call in calls
    )


def test_interpretation_date_cutoff() -> None:
    assert parse_interpretation_date("2014.01.01") is not None
    assert is_interpretation_on_or_after("2014-01-01")
    assert is_interpretation_on_or_after("20140102")
    assert not is_interpretation_on_or_after("2013-12-31")
    assert not is_interpretation_on_or_after("")


def test_cosine_collector_forwards_start_date(monkeypatch) -> None:
    target_collection = object()
    received: dict = {}

    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "get_cosine_interpretation_collection",
        lambda collection_name: target_collection,
    )
    monkeypatch.setattr(
        nts_interpretation_cosine_collector,
        "collect_and_store",
        lambda **kwargs: received.update(kwargs),
    )

    collect_cosine = (
        nts_interpretation_cosine_collector.
        collect_and_store_interpretations_cosine
    )
    collect_cosine(
        query="증여",
        start_page=1,
        end_page=2,
        start_date="2014-01-01",
    )

    assert received["target_collection"] is target_collection
    assert received["start_date"] == "2014-01-01"


def test_old_interpretation_chunks_are_selected_for_deletion() -> None:
    collection = SimpleNamespace(
        get=lambda include: {
            "ids": ["old", "cutoff", "new", "unknown"],
            "metadatas": [
                {"interpretation_date": "2013-12-31"},
                {"interpretation_date": "2014-01-01"},
                {"interpretation_date": "2020-05-01"},
                {"interpretation_date": ""},
            ],
        }
    )

    ids = find_interpretation_chunk_ids_before(collection)

    assert ids == ["old"]
