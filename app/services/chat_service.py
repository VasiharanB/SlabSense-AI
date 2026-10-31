
import asyncio
import logging
import random

from app.llm.gemini_client import (
    GeminiProvider,
    get_error_status_code,
    is_retryable_provider_error,
)
from app.schemas import ChatResponse, TokenUsage

logger = logging.getLogger(__name__)


SLABSENSE_SYSTEM_PROMPT = """
You are the general-purpose AI assistant powering SlabSense,
a Tamil Nadu electricity tariff and regulations support project.

At this stage, you do not have access to indexed regulatory
documents, tariff tables, subsidy orders, consumer bills,
or verified citation data.

Answer general educational questions clearly.

For specific electricity tariff rates, subsidy amounts,
slab thresholds, effective dates, legal requirements,
or individual bill calculations:

- Do not invent facts or figures.
- Clearly explain that the answer is not yet verified
  against the applicable official regulatory documents.
- Do not fabricate document references or page citations.

Never claim that an answer is grounded in official
regulatory documents unless supporting evidence
has actually been provided.
"""


class ChatService:
    """Coordinates Gemini generation, retries and fallback."""

    def __init__(
        self,
        provider: GeminiProvider,
        fallback_provider: GeminiProvider | None = None,
        max_retries: int = 1,
        retry_initial_delay_seconds: float = 1.0,
        retry_max_delay_seconds: float = 4.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        if retry_initial_delay_seconds <= 0:
            raise ValueError("Initial retry delay must be positive.")

        if retry_max_delay_seconds <= 0:
            raise ValueError("Maximum retry delay must be positive.")

        self.provider = provider
        self.fallback_provider = fallback_provider
        self.max_retries = max_retries
        self.retry_initial_delay_seconds = retry_initial_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds

    async def _generate_with_retries(
        self,
        provider: GeminiProvider,
        prompt: str,
        provider_role: str,
    ):
        """Attempt generation with bounded exponential backoff."""

        total_attempts = self.max_retries + 1

        for attempt_number in range(1, total_attempts + 1):
            try:
                return await provider.generate_text(prompt)

            except Exception as exc:
                retryable = is_retryable_provider_error(exc)

                if not retryable or attempt_number == total_attempts:
                    raise

                base_delay = min(
                    self.retry_initial_delay_seconds
                    * (2 ** (attempt_number - 1)),
                    self.retry_max_delay_seconds,
                )

                jitter = random.uniform(
                    0.0,
                    min(base_delay * 0.25, 1.0),
                )

                delay = min(
                    base_delay + jitter,
                    self.retry_max_delay_seconds,
                )

                logger.warning(
                    "Temporary Gemini failure. "
                    "role=%s model=%s next_attempt=%s total_attempts=%s "
                    "status_code=%s delay_seconds=%.2f",
                    provider_role,
                    provider.model,
                    attempt_number + 1,
                    total_attempts,
                    get_error_status_code(exc),
                    delay,
                )

                await asyncio.sleep(delay)

        raise RuntimeError(
            "Gemini generation exhausted its retry budget."
        )

    async def generate_reply(self, message: str) -> ChatResponse:
        """Generate a response using the primary or fallback model."""

        prompt = (
            f"{SLABSENSE_SYSTEM_PROMPT}\n\n"
            f"User question:\n{message}"
        )

        fallback_used = False

        try:
            result = await self._generate_with_retries(
                provider=self.provider,
                prompt=prompt,
                provider_role="primary",
            )

        except Exception as primary_error:
            if (
                self.fallback_provider is None
                or not is_retryable_provider_error(primary_error)
            ):
                raise

            logger.warning(
                "Primary Gemini model exhausted retries. "
                "Switching to fallback model=%s",
                self.fallback_provider.model,
            )

            result = await self._generate_with_retries(
                provider=self.fallback_provider,
                prompt=prompt,
                provider_role="fallback",
            )

            fallback_used = True

        return ChatResponse(
            answer=result.text,
            model=result.model,
            usage=TokenUsage(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.total_tokens,
                thought_tokens=result.usage.thought_tokens,
                tool_use_tokens=result.usage.tool_use_tokens,
                cached_tokens=result.usage.cached_tokens,
            ),
            fallback_used=fallback_used,
            grounded=False,
            sources=[],
        )
