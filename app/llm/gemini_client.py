from collections.abc import AsyncIterator
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
    """Raised when Gemini does not return a usable response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


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


@dataclass(frozen=True, slots=True)
class GeminiStreamEvent:
    """A text delta or the final completed interaction."""

    text: str | None = None
    result: GeminiTextResult | None = None


def _build_usage(usage: object | None) -> GeminiUsage:
    """Convert the SDK usage object into our application schema."""

    return GeminiUsage(
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


def _stream_error_status(error_code: object) -> int | None:
    """Map known Gemini stream error codes to HTTP status codes."""

    value = str(error_code or "").strip().lower()

    if value.isdigit():
        return int(value)

    return {
        "gateway_timeout": 504,
        "deadline_exceeded": 504,
        "resource_exhausted": 429,
        "too_many_requests": 429,
        "rate_limit_exceeded": 429,
        "unavailable": 503,
        "service_unavailable": 503,
        "internal": 500,
    }.get(value)


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
        """Generate a single-turn non-streaming response."""

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

        return GeminiTextResult(
            interaction_id=interaction.id,
            text=generated_text,
            model=interaction.model or self.model,
            usage=_build_usage(interaction.usage),
        )

    async def stream_text(
        self,
        prompt: str,
    ) -> AsyncIterator[GeminiStreamEvent]:
        """Stream text deltas and return final interaction metadata."""

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        stream = await self._async_client.interactions.create(
            model=self.model,
            input=prompt,
            store=False,
            stream=True,
            timeout=self.timeout_seconds,
        )

        collected_text: list[str] = []
        completed = False

        async for event in stream:
            event_type = getattr(event, "event_type", None)

            if event_type == "step.delta":
                delta = getattr(event, "delta", None)

                if getattr(delta, "type", None) == "text":
                    chunk = getattr(delta, "text", "") or ""

                    if chunk:
                        collected_text.append(chunk)
                        yield GeminiStreamEvent(text=chunk)

            elif event_type == "interaction.completed":
                interaction = getattr(event, "interaction", None)

                if interaction is None:
                    raise GeminiProviderError(
                        "Gemini stream completed without interaction metadata."
                    )

                generated_text = "".join(collected_text)

                if not generated_text.strip():
                    raise GeminiProviderError(
                        "Gemini completed the stream without text output."
                    )

                result = GeminiTextResult(
                    interaction_id=str(
                        getattr(interaction, "id", "") or ""
                    ),
                    text=generated_text,
                    model=getattr(
                        interaction,
                        "model",
                        None,
                    ) or self.model,
                    usage=_build_usage(
                        getattr(interaction, "usage", None)
                    ),
                )

                completed = True

                yield GeminiStreamEvent(result=result)
                break

            elif event_type == "error":
                error_data = getattr(event, "error", None)

                error_message = (
                    getattr(error_data, "message", None)
                    or "Gemini streaming interaction failed."
                )

                error_code = getattr(
                    error_data,
                    "code",
                    None,
                )

                raise GeminiProviderError(
                    str(error_message),
                    status_code=_stream_error_status(error_code),
                )

        if not completed:
            raise GeminiProviderError(
                "Gemini stream ended without an interaction.completed event."
            )

    async def aclose(self) -> None:
        """Close both SDK clients."""

        await self._async_client.aclose()
        self._client.close()