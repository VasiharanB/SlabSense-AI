
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import types

from app.config import Settings

RETRYABLE_HTTP_STATUS_CODES = frozenset(
    {408, 429, 500, 502, 503, 504}
)

TRANSIENT_ERROR_NAMES = frozenset(
    {"APIConnectionError", "APITimeoutError"}
)


class GeminiProviderError(RuntimeError):
    """Raised when Gemini does not return a usable text response."""


def _exception_chain(error: BaseException):
    """Walk through the original exception and its causes."""

    pending = [error]
    visited = set()

    while pending:
        current = pending.pop()

        if id(current) in visited:
            continue

        visited.add(id(current))
        yield current

        if current.__cause__ is not None:
            pending.append(current.__cause__)

        if current.__context__ is not None:
            pending.append(current.__context__)


def get_error_status_code(error: Exception) -> int | None:
    """Extract an HTTP status code from an SDK error or its cause."""

    for current in _exception_chain(error):
        for attribute in ("status_code", "code"):
            value = getattr(current, attribute, None)

            if isinstance(value, int):
                return value

            if isinstance(value, str) and value.isdigit():
                return int(value)

    return None


def is_retryable_provider_error(error: Exception) -> bool:
    """Return True only for temporary API or transport failures."""

    for current in _exception_chain(error):
        status_code = get_error_status_code(current)

        if status_code in RETRYABLE_HTTP_STATUS_CODES:
            return True

        if isinstance(
            current,
            (
                httpx.TimeoutException,
                httpx.NetworkError,
                TimeoutError,
                ConnectionError,
            ),
        ):
            return True

        if current.__class__.__name__ in TRANSIENT_ERROR_NAMES:
            return True

    return False


def _token_value(usage: object | None, attribute: str) -> int:
    """Safely read a non-negative token count from Gemini usage."""

    if usage is None:
        return 0

    value = getattr(usage, attribute, 0)

    try:
        result = int(value or 0)
    except (TypeError, ValueError):
        return 0

    return max(result, 0)


@dataclass(frozen=True, slots=True)
class GeminiUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

    thought_tokens: int = 0
    tool_use_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True, slots=True)
class GeminiTextResult:
    interaction_id: str
    text: str
    model: str
    usage: GeminiUsage


class GeminiProvider:
    """Async adapter for Google's Gemini Interactions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key cannot be empty.")

        if not model.strip():
            raise ValueError("Gemini model cannot be empty.")

        if timeout_seconds <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self.model = model
        self.timeout_seconds = timeout_seconds

        # Disable SDK-level retries.
        # ChatService controls the application retry budget.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=0,
                )
            ),
        )

        self._async_client = self._client.aio

    @classmethod
    def from_settings(cls, settings: Settings) -> "GeminiProvider":
        """Build the primary provider from application settings."""

        if settings.gemini_api_key is None:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. "
                "Configure it in your local .env file."
            )

        return cls(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )

    async def generate_text(self, prompt: str) -> GeminiTextResult:
        """Generate a single-turn text response from Gemini."""

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        interaction = await self._async_client.interactions.create(
            model=self.model,
            input=prompt,
            store=False,
            timeout=self.timeout_seconds,
        )

        generated_text = interaction.output_text or ""

        if not generated_text.strip():
            raise GeminiProviderError(
                "Gemini completed the interaction without text output."
            )

        usage = interaction.usage

        gemini_usage = GeminiUsage(
            input_tokens=_token_value(
                usage,
                "total_input_tokens",
            ),
            output_tokens=_token_value(
                usage,
                "total_output_tokens",
            ),
            thought_tokens=_token_value(
                usage,
                "total_thought_tokens",
            ),
            tool_use_tokens=_token_value(
                usage,
                "total_tool_use_tokens",
            ),
            cached_tokens=_token_value(
                usage,
                "total_cached_tokens",
            ),
            total_tokens=_token_value(
                usage,
                "total_tokens",
            ),
        )

        return GeminiTextResult(
            interaction_id=interaction.id,
            text=generated_text,
            model=interaction.model or self.model,
            usage=gemini_usage,
        )

    async def aclose(self) -> None:
        """Close both SDK clients."""

        await self._async_client.aclose()
        self._client.close()
