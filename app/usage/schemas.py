
from pydantic import BaseModel, Field


class UsageSummary(BaseModel):
    request_count: int = Field(ge=0)
    fallback_request_count: int = Field(ge=0)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    thought_tokens: int = Field(ge=0)
    tool_use_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    reported_total_tokens: int = Field(ge=0)

    estimated_cost_usd: str | None
    known_priced_cost_usd: str
    unpriced_request_count: int = Field(ge=0)
    cost_estimate_complete: bool

    currency: str = "USD"
    pricing_tiers: list[str] = Field(default_factory=list)


class UsageModelSummary(BaseModel):
    model: str

    request_count: int = Field(ge=0)
    fallback_request_count: int = Field(ge=0)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    thought_tokens: int = Field(ge=0)
    tool_use_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    reported_total_tokens: int = Field(ge=0)

    estimated_cost_usd: str | None
    known_priced_cost_usd: str
    unpriced_request_count: int = Field(ge=0)
    cost_estimate_complete: bool

    pricing_tiers: list[str] = Field(default_factory=list)


class RecentUsageRecord(BaseModel):
    request_id: str
    created_at: str
    model: str

    input_tokens: int
    output_tokens: int
    thought_tokens: int
    tool_use_tokens: int
    cached_tokens: int
    total_tokens: int

    fallback_used: bool
    pricing_tier: str

    estimated_cost_usd: str | None
    cost_estimate_complete: bool
    cost_estimate_note: str | None


class UsageResponse(BaseModel):
    summary: UsageSummary
    models: list[UsageModelSummary]
    recent_requests: list[RecentUsageRecord]
