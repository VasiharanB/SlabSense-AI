
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routers.usage import router as usage_router
from app.schemas import ChatResponse, TokenUsage
from app.usage.pricing import UsagePricingCalculator
from app.usage.repository import SQLiteUsageRepository
from app.usage.service import UsageService


def create_usage_service(
    tmp_path,
    pricing_tier: str = "standard_paid",
) -> UsageService:
    """Create an isolated usage service for testing."""

    settings = Settings(
        _env_file=None,
        usage_pricing_tier=pricing_tier,
    )

    repository = SQLiteUsageRepository(
        database_path=str(tmp_path / "test_usage.sqlite3"),
    )
    repository.initialize()

    pricing_calculator = UsagePricingCalculator(settings)

    return UsageService(
        repository=repository,
        pricing_calculator=pricing_calculator,
    )


def create_chat_response(
    model: str = "gemini-3.5-flash-lite",
    fallback_used: bool = False,
    input_tokens: int = 100,
    output_tokens: int = 200,
    thought_tokens: int = 20,
    cached_tokens: int = 0,
    tool_use_tokens: int = 0,
    request_id: UUID | None = None,
) -> ChatResponse:
    """Create a sample chat response for usage tests."""

    response_data = {
        "answer": "Sample answer for usage testing.",
        "model": model,
        "usage": TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thought_tokens=thought_tokens,
            tool_use_tokens=tool_use_tokens,
            cached_tokens=cached_tokens,
            total_tokens=(
                input_tokens
                + output_tokens
                + thought_tokens
                + tool_use_tokens
            ),
        ),
        "fallback_used": fallback_used,
        "grounded": False,
        "sources": [],
    }

    if request_id is not None:
        response_data["request_id"] = request_id

    return ChatResponse(**response_data)


def test_primary_model_usage_and_cost_are_recorded(tmp_path):
    service = create_usage_service(tmp_path)

    response = create_chat_response()

    inserted = service.record_chat(response)

    usage = service.get_usage()

    assert inserted is True
    assert usage.summary.request_count == 1
    assert usage.summary.input_tokens == 100
    assert usage.summary.output_tokens == 200
    assert usage.summary.thought_tokens == 20

    assert usage.summary.estimated_cost_usd == "0.000580000000"
    assert usage.summary.cost_estimate_complete is True

    assert usage.models[0].model == "gemini-3.5-flash-lite"


def test_real_fallback_model_usage_is_priced(tmp_path):
    service = create_usage_service(tmp_path)

    response = create_chat_response(
        model="gemini-3.6-flash",
        fallback_used=True,
    )

    service.record_chat(response)

    usage = service.get_usage()

    assert usage.summary.request_count == 1
    assert usage.summary.fallback_request_count == 1

    assert usage.models[0].model == "gemini-3.6-flash"
    assert usage.models[0].fallback_request_count == 1

    assert usage.summary.estimated_cost_usd == "0.000900000000"
    assert usage.summary.cost_estimate_complete is True


def test_cached_input_tokens_use_cached_pricing(tmp_path):
    service = create_usage_service(tmp_path)

    response = create_chat_response(
        input_tokens=100,
        output_tokens=200,
        thought_tokens=0,
        cached_tokens=40,
    )

    service.record_chat(response)

    usage = service.get_usage()

    assert usage.summary.cached_tokens == 40
    assert usage.summary.estimated_cost_usd == "0.000519200000"
    assert usage.summary.cost_estimate_complete is True


def test_unknown_model_is_marked_unpriced(tmp_path):
    service = create_usage_service(tmp_path)

    response = create_chat_response(
        model="fallback-model",
        fallback_used=True,
    )

    service.record_chat(response)

    usage = service.get_usage()

    assert usage.summary.request_count == 1
    assert usage.summary.unpriced_request_count == 1
    assert usage.summary.estimated_cost_usd is None
    assert usage.summary.cost_estimate_complete is False

    assert usage.recent_requests[0].model == "fallback-model"
    assert usage.recent_requests[0].estimated_cost_usd is None


def test_duplicate_request_is_not_counted_twice(tmp_path):
    service = create_usage_service(tmp_path)

    response = create_chat_response(
        request_id=UUID("11111111-1111-4111-8111-111111111111"),
    )

    first_insert = service.record_chat(response)
    second_insert = service.record_chat(response)

    usage = service.get_usage()

    assert first_insert is True
    assert second_insert is False
    assert usage.summary.request_count == 1


def test_free_tier_cost_is_zero(tmp_path):
    service = create_usage_service(
        tmp_path,
        pricing_tier="free_tier",
    )

    response = create_chat_response()

    service.record_chat(response)

    usage = service.get_usage()

    assert usage.summary.estimated_cost_usd == "0.000000000000"
    assert usage.summary.cost_estimate_complete is True
    assert usage.summary.pricing_tiers == ["free_tier"]


def test_usage_endpoint_returns_persisted_records(tmp_path):
    service = create_usage_service(tmp_path)

    service.record_chat(create_chat_response())

    app = FastAPI()
    app.state.usage_service = service
    app.include_router(usage_router)

    with TestClient(app) as client:
        response = client.get(
            "/usage",
            params={"recent_limit": 5},
        )

    assert response.status_code == 200

    data = response.json()

    assert data["summary"]["request_count"] == 1
    assert data["models"][0]["model"] == "gemini-3.5-flash-lite"
    assert len(data["recent_requests"]) == 1


def test_usage_endpoint_rejects_invalid_recent_limit(tmp_path):
    service = create_usage_service(tmp_path)

    app = FastAPI()
    app.state.usage_service = service
    app.include_router(usage_router)

    with TestClient(app) as client:
        response = client.get(
            "/usage",
            params={"recent_limit": 101},
        )

    assert response.status_code == 422
