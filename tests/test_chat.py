
from app.config import Settings, get_settings
from app.llm.gemini_client import GeminiTextResult, GeminiUsage
from app.main import app
from app.routers.chat import (
    get_gemini_fallback_provider,
    get_gemini_provider,
)


class FakeProviderError(Exception):
    """Simulated HTTP error from a Gemini provider."""

    def __init__(self, status_code: int):
        super().__init__(f"Simulated provider error: {status_code}")
        self.status_code = status_code


class FakeGeminiProvider:
    """Predictable provider that returns or raises queued outcomes."""

    def __init__(self, outcomes, model="fake-gemini-model"):
        self.outcomes = list(outcomes)
        self.model = model
        self.calls = 0

    async def generate_text(self, prompt: str) -> GeminiTextResult:
        assert "User question:" in prompt

        self.calls += 1

        if not self.outcomes:
            raise AssertionError("No fake provider outcomes remain.")

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


def make_result(model="gemini-3.5-flash-lite"):
    return GeminiTextResult(
        interaction_id="test-interaction-123",
        text="Electricity tariffs use applicable consumption slabs.",
        model=model,
        usage=GeminiUsage(
            input_tokens=20,
            output_tokens=15,
            total_tokens=35,
        ),
    )


def override_chat_dependencies(monkeypatch, primary, fallback=None):
    """Install fake providers and fast retry settings for tests."""

    settings = Settings(
        app_name="slabsense",
        environment="test",
        gemini_max_retries=1,
        gemini_retry_initial_delay_seconds=0.001,
        gemini_retry_max_delay_seconds=0.001,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_settings,
        lambda: settings,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_gemini_provider,
        lambda: primary,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_gemini_fallback_provider,
        lambda: fallback,
    )


def test_chat_returns_structured_response(client, monkeypatch):
    primary = FakeGeminiProvider([make_result()])

    override_chat_dependencies(monkeypatch, primary)

    response = client.post(
        "/chat",
        json={"message": "Explain electricity tariff slabs."},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == (
        "Electricity tariffs use applicable consumption slabs."
    )
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["usage"]["total_tokens"] == 35
    assert body["fallback_used"] is False
    assert body["grounded"] is False
    assert body["sources"] == []
    assert body["request_id"]


def test_chat_rejects_empty_message(client):
    response = client.post(
        "/chat",
        json={"message": "   "},
    )

    assert response.status_code == 422


def test_chat_rejects_unexpected_fields(client):
    response = client.post(
        "/chat",
        json={
            "message": "Explain tariff slabs.",
            "unexpected_field": "invalid",
        },
    )

    assert response.status_code == 422


def test_primary_retries_once_then_succeeds(client, monkeypatch):
    primary = FakeGeminiProvider(
        [
            FakeProviderError(503),
            make_result(),
        ]
    )

    override_chat_dependencies(monkeypatch, primary)

    response = client.post(
        "/chat",
        json={"message": "Explain tariff slabs."},
    )

    assert response.status_code == 200
    assert primary.calls == 2
    assert response.json()["fallback_used"] is False


def test_fallback_used_after_primary_retries_exhausted(
    client,
    monkeypatch,
):
    primary = FakeGeminiProvider(
        [
            FakeProviderError(503),
            FakeProviderError(503),
        ],
        model="primary-model",
    )

    fallback = FakeGeminiProvider(
        [make_result(model="fallback-model")],
        model="fallback-model",
    )

    override_chat_dependencies(
        monkeypatch,
        primary,
        fallback,
    )

    response = client.post(
        "/chat",
        json={"message": "Explain tariff slabs."},
    )

    assert response.status_code == 200
    assert primary.calls == 2
    assert fallback.calls == 1

    body = response.json()

    assert body["model"] == "fallback-model"
    assert body["fallback_used"] is True


def test_permanent_error_does_not_retry_or_use_fallback(
    client,
    monkeypatch,
):
    primary = FakeGeminiProvider(
        [FakeProviderError(403)],
        model="primary-model",
    )

    fallback = FakeGeminiProvider(
        [make_result(model="fallback-model")],
        model="fallback-model",
    )

    override_chat_dependencies(
        monkeypatch,
        primary,
        fallback,
    )

    response = client.post(
        "/chat",
        json={"message": "Explain tariff slabs."},
    )

    assert response.status_code == 502
    assert primary.calls == 1
    assert fallback.calls == 0


def test_both_models_fail_safely(client, monkeypatch):
    primary = FakeGeminiProvider(
        [
            FakeProviderError(503),
            FakeProviderError(503),
        ],
        model="primary-model",
    )

    fallback = FakeGeminiProvider(
        [
            FakeProviderError(503),
            FakeProviderError(503),
        ],
        model="fallback-model",
    )

    override_chat_dependencies(
        monkeypatch,
        primary,
        fallback,
    )

    response = client.post(
        "/chat",
        json={"message": "Explain tariff slabs."},
    )

    assert response.status_code == 502
    assert primary.calls == 2
    assert fallback.calls == 2
