# Spring ↔ FastAPI AI 상담 API 계약

- 기준 버전: FastAPI API v1
- Base path: `/api/v1`
- Content-Type: `application/json`
- JSON 필드명: `snake_case`

## 1. 전체 통신 흐름

```text
최초 질문
Spring → POST /api/v1/chat → FastAPI

응답 status == COMPLETED
→ answer를 사용자에게 표시하고 종료

응답 status == CLARIFICATION_REQUIRED
→ clarification_questions를 사용자에게 표시
→ 사용자의 답을 answers로 구성
→ POST /api/v1/chat/clarification

응답 status == REJECTED
→ answer의 안내 메시지를 사용자에게 표시
```

`CLARIFICATION_REQUIRED`는 오류가 아니라 정상적인 처리 결과이므로 HTTP
상태 코드는 `200 OK`다.

완료 여부를 나타내는 별도의 `completed` boolean 필드는 없다. Spring은 반드시
다음 조건으로 완료 여부를 판단한다.

```text
status == "COMPLETED"
```

## 2. conversation_id 규칙

- 최초 요청은 `conversation_id`를 `null`로 전송한다.
- FastAPI는 UUID 형식의 `conversation_id`를 생성해 응답한다.
- 추가 질문에 답할 때 응답받은 `conversation_id`를 그대로 다시 전송한다.
- 이 값은 OpenAI의 `response.id`가 아니라 FastAPI 애플리케이션의 대화 ID다.
- 현재 FastAPI는 이 ID로 대화 상태를 DB에서 복원하지 않는다.
- 따라서 `/chat/clarification` 요청에는 `conversation_id`뿐만 아니라 원래
  `question`, `intent`, `requires_calculation`, 기존 `facts`, 사용자 `answers`를
  모두 다시 전송해야 한다.

## 3. 최초 질문 API

```http
POST /api/v1/chat
Content-Type: application/json
```

### 3.1 Request

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `conversation_id` | `string \| null` | X | 최초 요청은 `null` 또는 생략 |
| `question` | `string` | O | 1~2,000자의 사용자 질문 |
| `families` | `array` | X | 등록 가족 목록. 생략 가능, 최대 3명 |
| `product` | `object \| null` | X | 선택 금융상품 정보 |
| `facts` | `object` | X | Spring이 이미 알고 있는 추가 사실 |

`families`가 없으면 필드를 생략하거나 빈 배열 `[]`을 전송한다. 명시적인
`null`은 허용하지 않으며 `422 Unprocessable Entity`가 반환된다.

```json
{
  "conversation_id": null,
  "question": "민지에게 2000만원 증여하면 증여세가 얼마나 나오나요?",
  "families": [
    {
      "family_id": 1,
      "name": "김민수",
      "relationship_type": "parent_to_adult_child",
      "gift_amount": 60000000,
      "recipient_age": 30,
      "recipient_is_minor": false,
      "has_previous_gifts": false,
      "previous_gift_amount": null,
      "previous_gift_date": null,
      "previous_gift_same_donor": null,
      "previously_used_deduction": 0,
      "deduction_renewal_date": null
    },
    {
      "family_id": 2,
      "name": "김민지",
      "relationship_type": "parent_to_adult_child",
      "gift_amount": 30000000,
      "recipient_age": 25,
      "recipient_is_minor": false,
      "has_previous_gifts": true,
      "previous_gift_amount": 10000000,
      "previous_gift_date": "2023-05-01",
      "previous_gift_same_donor": true,
      "previously_used_deduction": 10000000,
      "deduction_renewal_date": "2033-05-01"
    }
  ],
  "product": null,
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true
  }
}
```

### 3.2 FamilyData

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `family_id` | `integer` | O | 등록 가족 ID |
| `name` | `string` | O | 가족 이름 |
| `relationship_type` | `string` | O | 증여자와 수증자의 관계 코드 |
| `gift_amount` | `integer \| null` | X | 해당 가족의 기본 또는 계획 증여금액 |
| `recipient_age` | `integer \| null` | X | 수증자 나이, 0~150 |
| `recipient_is_minor` | `boolean \| null` | X | 미성년 여부 |
| `has_previous_gifts` | `boolean \| null` | X | 과거 증여 존재 여부 |
| `previous_gift_amount` | `integer \| null` | X | 과거 증여금액 |
| `previous_gift_date` | `date \| null` | X | 과거 증여일, `YYYY-MM-DD` |
| `previous_gift_same_donor` | `boolean \| null` | X | 현재와 동일 증여자인지 여부 |
| `previously_used_deduction` | `integer` | X | 기존 사용 공제액, 기본값 `0` |
| `deduction_renewal_date` | `date \| null` | X | 공제 갱신 기준일, `YYYY-MM-DD` |

권장 `relationship_type` 값:

| 값 | 의미 |
|---|---|
| `spouse` | 배우자 |
| `parent_to_adult_child` | 부모 → 성년 자녀 |
| `parent_to_minor_child` | 부모 → 미성년 자녀 |
| `child_to_parent` | 자녀 → 부모 |
| `other_relative` | 기타 친족 |
| `other` | 그 외 관계 |

### 3.3 가족 이름 선택 규칙

- 질문의 전체 이름이 등록 가족 한 명과 일치하면 해당 가족을 사용한다.
- 성을 생략한 이름도 한 명만 식별되는 경우 사용할 수 있다.
- 예: 등록 이름이 `김민지`이고 질문에 `민지`가 있으면 김민지를 선택한다.
- `김민지`, `박민지`처럼 생략된 이름이 중복되면 임의로 선택하지 않는다.
- 선택된 가족의 계산 정보는 서버가 `facts`에 병합한다.
- 질문에서 직접 추출한 값과 `request.facts`는 등록 가족 정보보다 우선한다.

최초 질문의 사실 병합 우선순위는 다음과 같다. 오른쪽 값이 왼쪽 값을
덮어쓴다.

```text
서버 기본값
→ 이름으로 선택한 가족 정보
→ 질문에서 추출한 정보
→ request.facts
```

따라서 등록된 김민지의 `gift_amount`가 3,000만원이어도 질문에서
`민지에게 2,000만원`이라고 입력하면 현재 계산 금액은 2,000만원이다.

## 4. 공통 정상 Response

모든 정상 응답은 다음 구조를 사용한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `conversation_id` | `string` | FastAPI가 생성하거나 전달받은 대화 ID |
| `status` | `string` | `COMPLETED`, `CLARIFICATION_REQUIRED`, `REJECTED` |
| `intent` | `string` | 분류된 질문 유형 |
| `requires_calculation` | `boolean` | 세액 등의 수치 계산 필요 여부 |
| `answer` | `string \| null` | 완료 또는 거절 답변 |
| `clarification_questions` | `array` | 추가 질문 목록, 최대 3개 |
| `facts` | `object` | 현재까지 확인·정규화된 사실 |

`intent` 값:

```text
concept, family, product, assessment, procedure,
other_gift, other, jailbreak
```

`requires_calculation`은 완료 여부가 아니다. 완료 여부는 항상 `status`로
판단한다.

## 5. 시나리오 A: 등록 가족 정보로 바로 답변 완료

등록 가족 이름이 유일하게 매칭되고 계산 필수 정보가 모두 들어 있으면
추가 질문 없이 완료될 수 있다.

### Response

```json
{
  "conversation_id": "36615cfb-f447-4cd9-a0f8-1eff8ccf0414",
  "status": "COMPLETED",
  "intent": "family",
  "requires_calculation": true,
  "answer": "김민지님에게 2,000만원을 증여하는 경우의 간이 계산 결과는 ...",
  "clarification_questions": [],
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "recipient_name": "김민지",
    "gift_amount": 20000000,
    "relationship_type": "parent_to_adult_child",
    "recipient_age": 25,
    "recipient_is_minor": false,
    "has_previous_gifts": true,
    "previous_gift_amount": 10000000,
    "previous_gift_date": "2023-05-01",
    "previous_gift_same_donor": true,
    "previously_used_deduction": 10000000,
    "deduction_renewal_date": "2033-05-01"
  }
}
```

Spring 처리:

```java
if (response.status() == ChatStatus.COMPLETED) {
    return response.answer();
}
```

## 6. 시나리오 B: 추가 정보가 필요한 경우

### 최초 Request

```json
{
  "conversation_id": null,
  "question": "성인 아들에게 6000만원을 증여하면 증여세가 얼마인가요?",
  "families": [],
  "product": null,
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true
  }
}
```

### Response

```json
{
  "conversation_id": "ceddbc1a-b66c-4e74-8b6c-37a244c9421f",
  "status": "CLARIFICATION_REQUIRED",
  "intent": "assessment",
  "requires_calculation": true,
  "answer": null,
  "clarification_questions": [
    {
      "key": "has_previous_gifts",
      "data_type": "boolean",
      "question": "최근 10년 내 이전 증여가 있었나요?",
      "reason": "합산 대상 증여 여부를 확인하기 위해 필요합니다."
    }
  ],
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000,
    "recipient_is_minor": false,
    "recipient_age": null,
    "relationship_type": "parent_to_adult_child",
    "previously_used_deduction": 0
  }
}
```

## 7. clarification_questions와 data_type

| key | data_type | Spring 권장 타입 | 프론트 입력 예시 |
|---|---|---|---|
| `recipient_name` | `string` | `String` | 텍스트 또는 가족 선택 |
| `relationship_type` | `string` | `String` | 관계 선택 |
| `gift_amount` | `integer` | `Long` | 숫자 입력 |
| `recipient_age` | `integer` | `Integer` | 숫자 입력 |
| `previous_gift_amount` | `integer` | `Long` | 숫자 입력 |
| `recipient_is_minor` | `boolean` | `Boolean` | 예/아니요 |
| `has_previous_gifts` | `boolean` | `Boolean` | 예/아니요 |
| `previous_gift_same_donor` | `boolean` | `Boolean` | 예/아니요 |
| `gift_date` | `date` | `LocalDate` 또는 ISO 문자열 | 날짜 입력 |
| `previous_gift_date` | `date` | `LocalDate` 또는 ISO 문자열 | 날짜 입력 |

날짜는 JSON에서 `YYYY-MM-DD` 문자열로 전송한다. 금액은 쉼표나 `만원`
문자열이 아닌 원 단위 정수 전송을 권장한다.

## 8. 추가 질문 답변 API

```http
POST /api/v1/chat/clarification
Content-Type: application/json
```

### 8.1 Request

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `conversation_id` | `string` | O | 직전 응답의 ID |
| `question` | `string` | O | 사용자의 최초 질문 |
| `intent` | `string` | O | 직전 응답의 intent |
| `requires_calculation` | `boolean` | X | 직전 응답 값, 기본 `false` |
| `facts` | `object` | O | 직전 응답의 facts |
| `answers` | `object` | O | 사용자가 이번에 입력한 답변 |
| `families` | `array` | X | 최초 요청과 동일한 최신 가족 목록, 최대 3명 |
| `product` | `object \| null` | X | 최초 요청과 동일한 상품 정보 |

후속 요청의 사실 병합 우선순위:

```text
서버 기본값
→ 이름으로 선택한 가족 정보
→ request.facts
→ request.answers
```

`answers`가 가장 높은 우선순위를 갖는다.

### 8.2 이전 증여가 없는 경우 Request

```json
{
  "conversation_id": "ceddbc1a-b66c-4e74-8b6c-37a244c9421f",
  "question": "성인 아들에게 6000만원을 증여하면 증여세가 얼마인가요?",
  "intent": "assessment",
  "requires_calculation": true,
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000,
    "recipient_is_minor": false,
    "recipient_age": null,
    "relationship_type": "parent_to_adult_child",
    "previously_used_deduction": 0
  },
  "answers": {
    "has_previous_gifts": false
  },
  "families": [],
  "product": null
}
```

### 8.3 완료 Response

```json
{
  "conversation_id": "ceddbc1a-b66c-4e74-8b6c-37a244c9421f",
  "status": "COMPLETED",
  "intent": "assessment",
  "requires_calculation": true,
  "answer": "최근 10년 내 이전 증여가 없다면 간이 계산 결과는 ...",
  "clarification_questions": [],
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000,
    "recipient_is_minor": false,
    "recipient_age": null,
    "relationship_type": "parent_to_adult_child",
    "has_previous_gifts": false,
    "previous_gift_amount": 0,
    "previous_gift_date": "",
    "previous_gift_same_donor": false,
    "previously_used_deduction": 0
  }
}
```

## 9. 시나리오 C: 추가 답변 후에도 정보가 부족한 경우

사용자가 과거 증여가 있다고 답했지만 세부 정보가 없으면 FastAPI가 다시
`CLARIFICATION_REQUIRED`를 반환할 수 있다.

### Request

```json
{
  "conversation_id": "ceddbc1a-b66c-4e74-8b6c-37a244c9421f",
  "question": "성인 아들에게 6000만원을 증여하면 증여세가 얼마인가요?",
  "intent": "assessment",
  "requires_calculation": true,
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000,
    "recipient_is_minor": false,
    "relationship_type": "parent_to_adult_child"
  },
  "answers": {
    "has_previous_gifts": true
  },
  "families": []
}
```

### Response

```json
{
  "conversation_id": "ceddbc1a-b66c-4e74-8b6c-37a244c9421f",
  "status": "CLARIFICATION_REQUIRED",
  "intent": "assessment",
  "requires_calculation": true,
  "answer": null,
  "clarification_questions": [
    {
      "key": "previous_gift_amount",
      "data_type": "integer",
      "question": "이전 증여금액은 얼마인가요?",
      "reason": "합산할 증여금액을 계산하기 위해 필요합니다."
    },
    {
      "key": "previous_gift_date",
      "data_type": "date",
      "question": "이전 증여일은 언제인가요?",
      "reason": "합산 대상 기간을 판단하기 위해 필요합니다."
    },
    {
      "key": "previous_gift_same_donor",
      "data_type": "boolean",
      "question": "이전 증여자와 현재 증여자가 동일한가요?",
      "reason": "합산 대상 여부를 판단하기 위해 필요합니다."
    }
  ],
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000,
    "recipient_is_minor": false,
    "relationship_type": "parent_to_adult_child",
    "has_previous_gifts": true,
    "previously_used_deduction": 0
  }
}
```

Spring은 새로 받은 `facts`를 저장하고 다음 제출 때 다시 보내야 한다.

## 10. 시나리오 D: 지원하지 않는 질문

`other` 또는 `jailbreak`로 분류되면 HTTP `200 OK`와 `REJECTED`가 반환된다.

```json
{
  "conversation_id": "53093e83-46c6-4705-8e72-a3f91eab9f9f",
  "status": "REJECTED",
  "intent": "other",
  "requires_calculation": false,
  "answer": "증여세, 증여 절차, 등록 가족 또는 등록 금융상품 관련 질문을 입력해 주세요.",
  "clarification_questions": [],
  "facts": {}
}
```

## 11. 시나리오 E: 요청 검증 실패

예를 들어 `families: null`, 4명 이상의 가족, 잘못된 날짜 형식을 보내면
`422 Unprocessable Entity`가 반환된다.

### 잘못된 Request

```json
{
  "conversation_id": null,
  "question": "증여세가 얼마인가요?",
  "families": null
}
```

### Response

```json
{
  "success": false,
  "status_code": 422,
  "timestamp": "2026-08-03T01:50:21.262798+00:00",
  "path": "/api/v1/chat",
  "error": {
    "code": "REQUEST_VALIDATION_ERROR",
    "message": "요청 데이터 형식이 올바르지 않습니다.",
    "details": [
      {
        "type": "list_type",
        "loc": ["body", "families"],
        "msg": "Input should be a valid list",
        "input": null
      }
    ]
  }
}
```

## 12. HTTP 오류 코드

| HTTP 상태 | error.code 예시 | 처리 권장 |
|---|---|---|
| `422` | `REQUEST_VALIDATION_ERROR` | 요청 DTO 또는 필드 타입 확인 |
| `404` | 비즈니스 예외 코드 | 리소스 없음 안내 |
| `429` | `OPENAI_RATE_LIMIT` | 잠시 후 재시도 |
| `502` | `OPENAI_CONNECTION_ERROR`, `OPENAI_API_ERROR` | AI 서비스 장애 처리 |
| `503` | 컬렉션 관련 비즈니스 예외 코드 | RAG 저장소 준비 상태 확인 |
| `504` | `OPENAI_TIMEOUT`, `EXTERNAL_API_TIMEOUT` | 타임아웃 또는 재시도 처리 |
| `500` | `INTERNAL_SERVER_ERROR` | 서버 오류 안내 및 로그 확인 |

오류 응답 공통 구조:

```json
{
  "success": false,
  "status_code": 500,
  "timestamp": "ISO-8601 UTC timestamp",
  "path": "/api/v1/chat",
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "서버 내부 오류가 발생했습니다.",
    "details": null
  }
}
```

## 13. Spring DTO 예시

```java
public enum ChatStatus {
    COMPLETED,
    CLARIFICATION_REQUIRED,
    REJECTED
}
```

```java
public enum ClarificationDataType {
    @JsonProperty("string")
    STRING,

    @JsonProperty("integer")
    INTEGER,

    @JsonProperty("boolean")
    BOOLEAN,

    @JsonProperty("date")
    DATE
}
```

```java
public record FamilyData(
    Long familyId,
    String name,
    String relationshipType,
    Long giftAmount,
    Integer recipientAge,
    Boolean recipientIsMinor,
    Boolean hasPreviousGifts,
    Long previousGiftAmount,
    LocalDate previousGiftDate,
    Boolean previousGiftSameDonor,
    Long previouslyUsedDeduction,
    LocalDate deductionRenewalDate
) {}
```

```java
public record ChatRequest(
    String conversationId,
    String question,
    List<FamilyData> families,
    Object product,
    Map<String, Object> facts
) {}
```

```java
public record ClarificationQuestion(
    String key,
    ClarificationDataType dataType,
    String question,
    String reason
) {}
```

```java
public record ChatResponse(
    String conversationId,
    ChatStatus status,
    String intent,
    boolean requiresCalculation,
    String answer,
    List<ClarificationQuestion> clarificationQuestions,
    Map<String, Object> facts
) {}
```

```java
public record ClarificationRequest(
    String conversationId,
    String question,
    String intent,
    boolean requiresCalculation,
    Map<String, Object> facts,
    Map<String, Object> answers,
    List<FamilyData> families,
    Object product
) {}
```

Jackson에서 `snake_case` ↔ `camelCase` 변환을 전역 설정하지 않는다면
각 필드에 `@JsonProperty("conversation_id")` 같은 매핑을 추가해야 한다.

## 14. Spring 상태 분기 예시

```java
return switch (response.status()) {
    case COMPLETED -> ChatResult.completed(
        response.answer(),
        response.facts()
    );

    case CLARIFICATION_REQUIRED -> ChatResult.clarification(
        response.conversationId(),
        response.intent(),
        response.requiresCalculation(),
        response.clarificationQuestions(),
        response.facts()
    );

    case REJECTED -> ChatResult.rejected(
        response.answer()
    );
};
```

## 15. 구현 체크리스트

- 최초 요청의 `conversation_id`는 `null`로 보낸다.
- 가족이 없으면 `families: []`로 보내거나 필드를 생략한다.
- `families: null`은 보내지 않는다.
- 가족은 최대 3명이다.
- 후속 요청에는 최초 질문과 직전 응답 상태를 모두 다시 보낸다.
- `facts`와 `answers`의 값은 `data_type`에 맞는 JSON 타입을 사용한다.
- 날짜는 `YYYY-MM-DD`, 금액은 원 단위 정수를 사용한다.
- `CLARIFICATION_REQUIRED`는 HTTP 오류로 처리하지 않는다.
- 최종 완료는 `status == COMPLETED`로 판단한다.
- `requires_calculation`을 완료 여부로 사용하지 않는다.
- 매 응답에서 최신 `facts`를 다음 요청용 상태로 보관한다.
