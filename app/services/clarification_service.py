class ClarificationService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    def analyze(
        self,
        *,
        question: str,
        context: str,
        facts: dict,
        intent: str,
        requires_calculation: bool,
    ) -> ClarificationResult:
        if intent != "assessment":
            return ClarificationResult(
                needs_clarification=False,
                question=[],
                known_facts=[],
                reason="추가 확인 대상이 아닙니다."
            )

        prompt = build_clarification_prompt(
                question=question,
                context=context,
                additional_facts=additional_facts,
                intent=intent,
                requires_calculation=requires_calculation,
            )
        
        response = chat_client.responses.create(
            model=OPENAI_CHAT_MODEL,
            instructions=CLARIFICATION_SYSTEM_PROMPT,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "clarification_result",
                    "strict": True,
                    "schema": CLARIFICATION_SCHEMA,
                }
            },
        )
    
        if not response.output_text:
            raise RuntimeError(
                "추가정보 판정 결과가 비어 있습니다."
            )
    
        result = ClarificationResult.model_validate_json(
            response.output_text
        )
    
        if result.needs_clarification:
            result.questions = result.questions[:3]
    
            if not result.questions:
                result.needs_clarification = False
    
        return result
        