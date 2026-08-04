# MiriZoom(미리줌) FastApi

증여세 관련 법령과 국세청 상담·FAQ 데이터를 기반으로 답변을 생성하는 FastAPI 기반 RAG(Retrieval-Augmented Generation) 서버입니다.

사용자의 질문과 관련된 문서를 ChromaDB에서 검색한 뒤, 검색된 문맥을 OpenAI 모델에 전달하여 증여세 관련 답변을 생성합니다.

> 본 프로젝트의 답변은 참고용이며, 세무사 또는 국세청의 공식 상담을 대체하지 않습니다.

Spring 연동 규격과 시나리오별 요청·응답 예시는
[SPRING_FASTAPI_API_CONTRACT.md](SPRING_FASTAPI_API_CONTRACT.md)를 참고하세요.

---

## 1. 주요 기능

* 증여세 관련 사용자 질문 처리
* 국가법령정보센터 법령 데이터 수집
* 국세청 FAQ 및 법령해석 데이터 수집
* 문서 전처리 및 청크 분할
* OpenAI Embedding API를 이용한 임베딩 생성
* ChromaDB 벡터 저장소 구축
* 사용자 질문과 유사한 문서 검색
* 검색된 법령과 FAQ를 기반으로 RAG 답변 생성
* Spring Framework 서버와 REST API 통신
* Markdown 문법 없이 프론트에서 바로 표시할 수 있는 AI 답변 생성
* 한국어 금액 표현을 원 단위 정수로 정규화한 서버 증여세 간이 계산
* 답변에 활용된 참고 문서 및 출처 반환

---

## 2. 시스템 아키텍처

```text
사용자
  ↓
Vue.js Frontend
  ↓
Spring Framework API Server
  ↓
FastAPI RAG Server
  ├─ 사용자 질문 임베딩
  ├─ ChromaDB 유사 문서 검색
  ├─ RAG 프롬프트 생성
  └─ OpenAI API 호출
  ↓
Spring Framework API Server
  ↓
Vue.js Frontend
```

### RAG 처리 흐름

```text
법령 및 FAQ 데이터 수집
  ↓
HTML·JSON 데이터 정제
  ↓
문서 청크 분할
  ↓
임베딩 벡터 생성
  ↓
ChromaDB 저장
  ↓
사용자 질문 입력
  ↓
질문 임베딩 생성
  ↓
유사 문서 Top-K 검색
  ↓
검색 문서 기반 프롬프트 생성
  ↓
LLM 답변 생성
```

---

## 3. 기술 스택

| 구분                    | 기술                       |
| --------------------- | ------------------------ |
| Language              | Python 3.12              |
| API Framework         | FastAPI                  |
| ASGI Server           | Uvicorn                  |
| Package Manager       | uv                       |
| LLM                   | OpenAI API               |
| Chat Model            | `gpt-5-nano`             |
| Embedding Model       | `text-embedding-3-small` |
| Vector Database       | ChromaDB                 |
| HTTP Client           | Requests 또는 HTTPX        |
| Data Validation       | Pydantic                 |
| Settings              | pydantic-settings        |
| HTML Parsing          | BeautifulSoup4           |
| Environment Variables | python-dotenv            |
| Test                  | pytest                   |

---

## 4. 프로젝트 구조

```text
gift-tax-rag-server/
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  ├─ dependencies.py
│  │  ├─ exception_handlers.py
│  │  └─ v1/endpoints/
│  │     ├─ health.py
│  │     └─ chat.py
│  ├─ collectors/
│  │  ├─ law_article_collector.py
│  │  ├─ law_article_cosine_collector.py
│  │  ├─ nts_interpretation_collector.py
│  │  └─ nts_interpretation_cosine_collector.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ constants.py
│  │  └─ exceptions.py
│  ├─ schemas/
│  │  ├─ chat.py
│  │  ├─ family.py
│  │  └─ product.py
│  ├─ services/
│  │  ├─ chat_service.py
│  │  ├─ retrieval_service.py
│  │  ├─ clarification_service.py
│  │  ├─ context_service.py
│  │  └─ answer_service.py
│  ├─ repositories/
│  │  ├─ law_repository.py
│  │  └─ interpretation_repository.py
│  └─ prompts/
├─ storage/
│  └─ chroma/
├─ tests/
│  └─ test_application.py
├─ .env.example
├─ .gitignore
├─ pyproject.toml
├─ uv.lock
└─ README.md
```

---

## 5. 시작하기

### 요구 사항

* Python 3.12 이상
* uv
* OpenAI API Key

### 저장소 복제

```bash
git clone https://github.com/{organization}/{repository}.git
cd gift-tax-rag-server
```

### uv 설치

#### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### macOS 또는 Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 가상환경 및 의존성 설치

```bash
uv sync
```

가상환경을 직접 활성화하려면 다음 명령어를 사용합니다.

#### Windows

```powershell
.venv\Scripts\activate
```

#### macOS 또는 Linux

```bash
source .venv/bin/activate
```

---

## 6. 환경 변수 설정

프로젝트 루트에서 `.env.example` 파일을 복사하여 `.env` 파일을 생성합니다.

```bash
cp .env.example .env
```

Windows PowerShell에서는 다음 명령어를 사용할 수 있습니다.

```powershell
Copy-Item .env.example .env
```

### `.env.example`

```env
APP_NAME=gift-tax-rag-server
APP_ENV=local
APP_HOST=0.0.0.0
APP_PORT=8000

OPENAI_API_KEY=your-openai-api-key
OPENAI_CHAT_MODEL=gpt-5-nano
OPENAI_EMBEDDING_API_KEY=your-openai-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

CHROMA_PATH=storage/chroma
LAW_COLLECTION_NAME=gift_tax_law_articles
INTERPRETATION_COLLECTION_NAME=gift_tax_documents
LAW_COSINE_COLLECTION_NAME=gift_tax_law_articles_cosine
INTERPRETATION_COSINE_COLLECTION_NAME=gift_tax_documents_cosine
INTERPRETATION_START_DATE=2014-01-01

INTERPRETATION_TOP_K=4
LAW_TOP_K=2
LAW_CHUNK_TOP_K=10

LAW_API_OC=your-law-api-oc
```

> `.env` 파일에는 API Key 등 민감한 정보가 포함되므로 Git에 커밋하지 않습니다.

법령 검색은 `LAW_CHUNK_TOP_K`개의 후보 청크를 가져온 뒤
`law_id + article_key` 기준으로 조문을 묶습니다. 같은 조문의 항과
분할 청크는 법령 순서대로 합치고, 최종적으로 `LAW_TOP_K`개 조문을
프롬프트에 적재합니다.

---

## 7. 애플리케이션 실행

### 개발 서버 실행

```bash
uv run uvicorn app.main:app --reload
```

호스트와 포트를 직접 지정할 수도 있습니다.

```bash
uv run uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

Windows PowerShell에서는 한 줄로 실행하는 것을 권장합니다.

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

서버 실행 후 다음 주소에서 확인할 수 있습니다.

```text
API Server: http://localhost:8000
Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc
```

---

## 8. 벡터 데이터 구축

RAG 검색에 사용할 법령과 FAQ 데이터는 서버 요청 전에 미리 수집하고 ChromaDB에 저장해야 합니다.

### 데이터 수집

```bash
uv run python -m app.collectors.law_article_collector
uv run python -m app.collectors.nts_interpretation_collector
```

기본 L2 컬렉션과 별도로 Cosine HNSW 컬렉션을 구축하려면
다음 Cosine 전용 collector 파일을 실행합니다.

```powershell
uv run python -m app.collectors.law_article_cosine_collector
uv run python -m app.collectors.nts_interpretation_cosine_collector
```

기본 Cosine 컬렉션 이름은 각각
`gift_tax_law_articles_cosine`, `gift_tax_documents_cosine`이며
`.env`의 `LAW_COSINE_COLLECTION_NAME`,
`INTERPRETATION_COSINE_COLLECTION_NAME`으로 변경할 수 있습니다.
서버 검색도 Cosine 컬렉션으로 전환하려면 `LAW_COLLECTION_NAME`과
`INTERPRETATION_COLLECTION_NAME`에 위 Cosine 컬렉션 이름을 지정합니다.

국세청 법령해석 collector는 `INTERPRETATION_START_DATE` 이전 문서를
목록 단계에서 제외하고, 상세 문서 날짜를 다시 검증한 뒤 저장합니다.
기존 L2/Cosine 컬렉션의 오래된 청크는 먼저 dry-run으로 확인합니다.

```powershell
uv run python -m scripts.prune_old_interpretations
```

출력된 삭제 대상을 확인한 후 실제로 삭제합니다.

```powershell
uv run python -m scripts.prune_old_interpretations --apply
```

수집된 원본 데이터는 다음 경로에 저장합니다.

```text
storage/raw/laws/
storage/raw/nts_interpretations/
```

수집기는 다음 작업을 한 번에 수행합니다.

1. 원본 문서 로드
2. HTML 태그 및 불필요한 문자열 제거
3. 문서를 일정한 크기의 청크로 분할
4. 각 청크의 임베딩 벡터 생성
5. ChromaDB 컬렉션에 저장
6. 문서 출처와 메타데이터 저장

### 저장 메타데이터 예시

```json
{
  "document_id": "law-001",
  "source_type": "LAW",
  "title": "상속세 및 증여세법 제53조",
  "source_url": "https://www.law.go.kr/...",
  "effective_date": "2026-01-01",
  "organization": "국가법령정보센터"
}
```

---

## 9. API 명세

### Health Check

서버 상태를 확인합니다.

```http
GET /api/v1/health
```

#### Response

```json
{
  "status": "UP"
}
```

---

### AI 상담 요청

사용자 질문을 입력받아 관련 법령과 FAQ를 검색하고 답변을 생성합니다.

```http
POST /api/v1/chat
Content-Type: application/json
```

#### Request

```json
{
  "conversation_id": null,
  "question": "김민수에게 6천만 원을 증여하면 증여세가 발생하나요?",
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
    }
  ],
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true
  }
}
```

`families`에는 최대 3명의 등록 가족 정보를 전달할 수 있습니다.
질문에 가족 이름이 포함되면 AI가 이름이 일치하는 가족 한 명의 정보만
사용합니다. 이름으로 대상을 특정할 수 없으면 대상 가족의 이름을
추가로 질문합니다.

#### Response

```json
{
  "conversation_id": "2d73489e-e605-40b6-9e39-4f61e024b134",
  "status": "COMPLETED",
  "intent": "assessment",
  "requires_calculation": true,
  "answer": "성년 자녀가 직계존속으로부터 증여받는 경우 일정 금액까지 증여재산공제가 적용될 수 있습니다.",
  "clarification_questions": [],
  "facts": {}
}
```

추가 정보가 필요한 경우 응답의 `conversation_id`, `intent`,
`requires_calculation`, `facts`를 유지하고 답변을 제출합니다.

추가 질문에는 Spring과 프론트가 입력값 형식을 결정할 수 있도록
`data_type`이 포함됩니다.

```json
{
  "status": "CLARIFICATION_REQUIRED",
  "clarification_questions": [
    {
      "key": "has_previous_gifts",
      "data_type": "boolean",
      "question": "최근 10년 내 이전 증여가 있었나요?",
      "reason": "합산 대상 증여 여부를 확인하기 위해 필요합니다."
    },
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
    }
  ]
}
```

```http
POST /api/v1/chat/clarification
Content-Type: application/json
```

```json
{
  "conversation_id": "2d73489e-e605-40b6-9e39-4f61e024b134",
  "question": "김민수에게 6천만 원을 증여하면 증여세가 발생하나요?",
  "intent": "family",
  "requires_calculation": true,
  "facts": {
    "residency": "국내 거주자",
    "use_latest_tax_rate": true,
    "gift_amount": 60000000
  },
  "answers": {
    "has_previous_gifts": false
  },
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
    }
  ]
}
```

---

## 10. 오류 응답

### 잘못된 요청

```http
400 Bad Request
```

```json
{
  "code": "INVALID_REQUEST",
  "message": "질문을 입력해 주세요.",
  "detail": null
}
```

### 관련 문서를 찾지 못한 경우

```http
404 Not Found
```

```json
{
  "code": "DOCUMENT_NOT_FOUND",
  "message": "질문과 관련된 문서를 찾을 수 없습니다.",
  "detail": null
}
```

### OpenAI API 호출 실패

```http
502 Bad Gateway
```

```json
{
  "code": "OPENAI_API_ERROR",
  "message": "AI 응답을 생성하는 중 오류가 발생했습니다.",
  "detail": null
}
```

### 서버 내부 오류

```http
500 Internal Server Error
```

```json
{
  "code": "INTERNAL_SERVER_ERROR",
  "message": "서버 내부 오류가 발생했습니다.",
  "detail": null
}
```

---

## 11. RAG 프롬프트 정책

LLM은 검색된 문서 범위 안에서 답변하도록 구성합니다.

### 기본 원칙

* 제공된 법령과 FAQ를 우선하여 답변합니다.
* 검색 문서에서 확인되지 않는 내용은 임의로 생성하지 않습니다.
* 확실하지 않은 내용은 확인이 필요하다고 안내합니다.
* 세무 판단이나 신고를 확정적으로 지시하지 않습니다.
* 답변에 활용한 법령 또는 FAQ 출처를 반환합니다.
* 법률 개정 가능성을 고려하여 문서의 시행일과 데이터 기준일을 확인합니다.

### 프롬프트 예시

```text
당신은 대한민국 증여세 상담을 보조하는 AI입니다.

다음 참고 문서를 기반으로 사용자의 질문에 답변하세요.

규칙:
1. 참고 문서에 없는 내용을 임의로 생성하지 마세요.
2. 답변의 근거가 되는 법령과 FAQ를 함께 제시하세요.
3. 불확실한 경우 세무사 또는 국세청에 확인이 필요하다고 안내하세요.
4. 법률 및 세율은 개정될 수 있다는 점을 명시하세요.
5. 사용자가 이해하기 쉬운 한국어로 설명하세요.

[참고 문서]
{context}

[사용자 질문]
{question}
```

---

## 12. Spring 서버 연동

Spring Framework 서버는 FastAPI 서버의 상담 API를 호출합니다.

### 요청 흐름

```text
Frontend
  → Spring
  → FastAPI
  → ChromaDB
  → OpenAI API
  → FastAPI
  → Spring
  → Frontend
```

### Spring에서 호출할 FastAPI 주소

```text
POST http://localhost:8000/api/v1/chat
```

운영 환경에서는 환경 변수 또는 설정 파일로 API 주소를 관리합니다.

```properties
fastapi.base-url=http://fastapi:8000
```

---

## 13. 테스트

전체 테스트를 실행합니다.

```bash
uv run pytest
```

상세 로그를 출력하려면 다음 명령어를 사용합니다.

```bash
uv run pytest -v
```

커버리지를 확인하려면 다음 명령어를 사용합니다.

```bash
uv run pytest --cov=app --cov-report=term-missing
```

Cosine 컬렉션을 대상으로 실제 임베딩 검색까지 검증하려면 다음과 같이
통합 테스트를 명시적으로 활성화합니다.

```powershell
$env:RUN_COSINE_RAG_TEST="1"
uv run pytest tests/test_gift_tax_rag_cosine.py -v -s
```

기존 `test_gift_tax_rag.py`의 대화형 상담 흐름을 Cosine 검색으로
실행하려면 다음 명령을 사용합니다.

```powershell
uv run python -m tests.test_gift_tax_rag_cosine
```

## 14. 보안 주의사항

* OpenAI API Key를 코드에 직접 작성하지 않습니다.
* `.env` 파일을 Git에 커밋하지 않습니다.
* 공개 저장소에 개인정보나 실제 상담 데이터를 업로드하지 않습니다.
* 질문 및 답변 로그에 개인정보가 포함되지 않도록 필터링합니다.
* 외부 API 요청에 타임아웃과 재시도 정책을 적용합니다.
* 운영 환경에서는 허용된 Spring 서버만 FastAPI에 접근하도록 제한합니다.
* 관리자용 데이터 재수집 및 ChromaDB 초기화 API는 외부에 공개하지 않습니다.

---

## 15. 브랜치 전략

```text
main
develop
feature/{JIRA-번호}_{기능명}
fix/{JIRA-번호}_{수정명}
refactor/{JIRA-번호}_{리팩터링명}
hotfix/{JIRA-번호}_{긴급수정명}
```

예시:

```text
feature/KAN-30_rag-consultation
feature/KAN-31_law-data-ingestion
fix/KAN-32_chroma-search
```

---

## 16. 커밋 메시지 규칙

```text
KAN-{번호} {type}: {메시지}
```

사용 가능한 타입:

| 타입         | 설명          |
| ---------- | ----------- |
| `feat`     | 새로운 기능      |
| `fix`      | 버그 수정       |
| `refactor` | 리팩터링        |

예시:

```text
KAN-30 feat: RAG 상담 API 구현
KAN-31 feat: 법령 데이터 임베딩 스크립트 추가
KAN-32 fix: ChromaDB 검색 결과 필터링 오류 수정
```

---

## 17. Pull Request 규칙

Pull Request에는 다음 내용을 작성합니다.

* 연관된 Jira 티켓
* 변경 목적
* 주요 변경 사항
* 테스트 방법
* API 변경 여부
* 환경 변수 변경 여부
* 리뷰어가 확인해야 할 사항

예시:

```markdown
## 연관 이슈

- KAN-30

## 작업 내용

- RAG 상담 API를 구현했습니다.
- ChromaDB에서 유사 문서 5개를 조회하도록 구현했습니다.
- 검색 결과를 기반으로 OpenAI 프롬프트를 생성합니다.

## 테스트

- 정상 질문 요청 테스트
- 질문 누락 테스트
- OpenAI API 오류 테스트
- 검색 결과가 없는 경우 테스트

## 참고 사항

- `.env`에 `OPENAI_API_KEY` 설정이 필요합니다.
```

---

## 18. 기여 방법

1. 저장소를 Fork하거나 작업 브랜치를 생성합니다.
2. `develop` 브랜치의 최신 내용을 반영합니다.
3. 기능 단위로 코드를 작성합니다.
4. 테스트와 정적 분석을 실행합니다.
5. 커밋 규칙에 맞춰 커밋합니다.
6. `develop` 브랜치를 대상으로 Pull Request를 생성합니다.
7. 리뷰 승인 및 필수 검사 통과 후 병합합니다.

---

## 19. 라이선스

이 프로젝트는 현재 외부 사용을 위한 라이선스가 정해지지 않았습니다.

```text
This project is currently not licensed for external use.
```

---

## 20. 면책 조항

이 서비스에서 제공하는 답변은 법률 또는 세무 자문이 아닌 참고 정보입니다.

실제 증여 신고, 세금 계산 및 재산 이전을 진행하기 전에는 국세청, 세무사 또는 관련 전문가에게 확인해야 합니다. 법령과 세율은 개정될 수 있으므로 최신 시행 법령을 기준으로 판단해야 합니다.
