from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.core.config import get_settings

def main() -> None:
    settings = get_settings()

    masked_key = {
        f"{settings.openai_api_key[:7]}..."
        f"{settings.openai_api_key[-4:]}"
    }

    print(f"API Key 로드 확인: {masked_key}")
    print(f"사용 모델: {settings.openai_chat_model}")

    client = OpenAI(
        api_key = settings.openai_api_key,
    )

    try:
        response = client.responses.create(
            model = settings.openai_chat_model,
            input=(
                "연결 테스트입니다. "
                "'llm 연결 성공'이라고 짧게 답변해 주세요"
            ),
        )

        print("\n응답:")
        print(response.output_text)

    except AuthenticationError:
        print(
            "인증에 실패했습니다."
            ".env의 OPENAI_API_KEY를 확인해 주세요."
        )
    
    except RateLimitError:
        print(
            "요청 한도 또는 결제 한도에 도달했습니다."
            "OpenAI 사용량과 결제 설정을 확인해 주세요."

        )

    except APIConnectionError as exception:
        print(
            "OpenAI 서버에 연결하지 못했습니다. "
            "인터넷, 프록시 또는 방화벽을 확인해 주세요."
        )
        print(f"상세 오류: {exception}")

    except APIStatusError as exception:
        print(
            f"OpenAI API 요청 실패: "
            f"HTTP {exception.status_code}"
        )
        print(f"상세 오류: {exception}")

    except Exception as exception:
        print(f"예상하지 못한 오류: {type(exception).__name__}")
        print(str(exception))


if __name__ == "__main__":
    main()