
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.config import Settings
from app.llm.gemini_client import GeminiUsage

MILLION = Decimal("1000000")
COST_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal


@dataclass(frozen=True, slots=True)
class CostEstimate:
    amount_usd: Decimal | None
    complete: bool
    note: str | None = None


class UsagePricingCalculator:
    """Calculate estimated model costs from reported token usage."""

    def __init__(self, settings: Settings) -> None:
        self.pricing_tier = settings.usage_pricing_tier

        if self.pricing_tier == "free_tier":
            free_price = Decimal("0")

            self._prices = {
                "gemini-3.5-flash-lite": ModelPricing(
                    input_usd_per_million=free_price,
                    output_usd_per_million=free_price,
                    cached_input_usd_per_million=free_price,
                ),
                "gemini-3.6-flash": ModelPricing(
                    input_usd_per_million=free_price,
                    output_usd_per_million=free_price,
                    cached_input_usd_per_million=free_price,
                ),
            }

        else:
            self._prices = {
                "gemini-3.5-flash-lite": ModelPricing(
                    input_usd_per_million=(
                        settings.gemini_35_flash_lite_input_usd_per_million
                    ),
                    output_usd_per_million=(
                        settings.gemini_35_flash_lite_output_usd_per_million
                    ),
                    cached_input_usd_per_million=(
                        settings.gemini_35_flash_lite_cached_input_usd_per_million
                    ),
                ),
                "gemini-3.6-flash": ModelPricing(
                    input_usd_per_million=(
                        settings.gemini_36_flash_input_usd_per_million
                    ),
                    output_usd_per_million=(
                        settings.gemini_36_flash_output_usd_per_million
                    ),
                    cached_input_usd_per_million=(
                        settings.gemini_36_flash_cached_input_usd_per_million
                    ),
                ),
            }

    @staticmethod
    def normalize_model(model: str) -> str:
        """Normalize a Gemini model identifier."""

        return model.removeprefix("models/").strip()

    def get_model_pricing(self, model: str) -> ModelPricing | None:
        """Return configured pricing for a model."""

        normalized_model = self.normalize_model(model)
        return self._prices.get(normalized_model)

    def estimate(
        self,
        model: str,
        usage: GeminiUsage,
    ) -> CostEstimate:
        """Estimate a request's cost in USD."""

        pricing = self.get_model_pricing(model)

        if pricing is None:
            return CostEstimate(
                amount_usd=None,
                complete=False,
                note="No pricing configuration exists for this model.",
            )

        if usage.tool_use_tokens > 0:
            return CostEstimate(
                amount_usd=None,
                complete=False,
                note=(
                    "Tool-use tokens are present. "
                    "Separate tool-use pricing is not modeled yet."
                ),
            )

        if usage.cached_tokens > usage.input_tokens:
            return CostEstimate(
                amount_usd=None,
                complete=False,
                note="Cached tokens exceed the reported input tokens.",
            )

        ordinary_input_tokens = (
            usage.input_tokens - usage.cached_tokens
        )

        billed_output_tokens = (
            usage.output_tokens + usage.thought_tokens
        )

        input_cost = (
            Decimal(ordinary_input_tokens)
            * pricing.input_usd_per_million
        )

        cached_input_cost = (
            Decimal(usage.cached_tokens)
            * pricing.cached_input_usd_per_million
        )

        output_cost = (
            Decimal(billed_output_tokens)
            * pricing.output_usd_per_million
        )

        amount = (
            (input_cost + cached_input_cost + output_cost) / MILLION
        ).quantize(
            COST_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        return CostEstimate(
            amount_usd=amount,
            complete=True,
        )
