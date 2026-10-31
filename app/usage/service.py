
from datetime import UTC, datetime

from app.llm.gemini_client import GeminiUsage
from app.schemas import ChatResponse
from app.usage.pricing import UsagePricingCalculator
from app.usage.repository import UsageRecord, UsageRepository
from app.usage.schemas import UsageResponse


class UsageService:
    """Record completed chats and provide usage summaries."""

    def __init__(
        self,
        repository: UsageRepository,
        pricing_calculator: UsagePricingCalculator,
    ) -> None:
        self.repository = repository
        self.pricing_calculator = pricing_calculator

    def record_chat(self, response: ChatResponse) -> bool:
        """Persist usage for a completed chat response."""

        usage = GeminiUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thought_tokens=response.usage.thought_tokens,
            tool_use_tokens=response.usage.tool_use_tokens,
            cached_tokens=response.usage.cached_tokens,
            total_tokens=response.usage.total_tokens,
        )

        estimate = self.pricing_calculator.estimate(
            model=response.model,
            usage=usage,
        )

        pricing = self.pricing_calculator.get_model_pricing(
            response.model
        )

        record = UsageRecord(
            request_id=str(response.request_id),
            created_at=datetime.now(UTC).isoformat(),
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            thought_tokens=usage.thought_tokens,
            tool_use_tokens=usage.tool_use_tokens,
            cached_tokens=usage.cached_tokens,
            total_tokens=usage.total_tokens,
            fallback_used=response.fallback_used,
            pricing_tier=self.pricing_calculator.pricing_tier,
            input_price_usd_per_million=(
                pricing.input_usd_per_million
                if pricing is not None
                else None
            ),
            output_price_usd_per_million=(
                pricing.output_usd_per_million
                if pricing is not None
                else None
            ),
            cached_input_price_usd_per_million=(
                pricing.cached_input_usd_per_million
                if pricing is not None
                else None
            ),
            estimated_cost_usd=estimate.amount_usd,
            cost_estimate_complete=estimate.complete,
            cost_estimate_note=estimate.note,
        )

        return self.repository.insert_record(record)

    def get_usage(self, recent_limit: int = 20) -> UsageResponse:
        """Return validated aggregate usage information."""

        snapshot = self.repository.get_snapshot(
            recent_limit=recent_limit,
        )

        return UsageResponse.model_validate(snapshot)
