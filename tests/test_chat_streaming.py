
import json

from app.config import Settings, get_settings
from app.llm.gemini_client import (
    GeminiStreamEvent,
    GeminiTextResult,
    GeminiUsage,
)
from app.main import app
from app.routers.chat import (
    get_gemini_fallback_provider,
    get_gemini_provider,
)


class FakeProviderError(Exception):
    """Simulated temporary Gemini provider error."""

    def __init__(self, status_code: int):
        super().__init__(
            f"Simulated provider error: {status_code}"
        )
        self.status_code = status_code


class FakeStreamingProvider:
    """Fake streaming Gemini provider for deterministic tests."""

    def __init__(
        self,
        attempts,
        model="fake-gemini-model",
    ):
        self.attempts = list(attempts)
        self.model = model
        self.calls = 0

    async def stream_text(self, prompt: str):
        assert "User question:" in prompt

        self.calls += 1

        if not self.attempts:
            raise AssertionError(
                "No fake streaming outcomes remain."
            )

        attempt = self.attempts.pop(0)
        collected = []

        for item in attempt:
            if isinstance(item, Exception):
                raise item

            collected.append(item)

            yield GeminiStreamEvent(text=item)

        result = GeminiTextResult(
            interaction_id=f"fake-interaction-{self.calls}",
            text="".join(collected),
            model=self.model,
            usage=GeminiUsage(
                input_tokens=25,
                output_tokens=20,
                total_tokens=45,
            ),
        )

        yield GeminiStreamEvent(result=result)


def override_stream_dependencies(
    monkeypatch,
    primary,
    fallback=None,
):
    """Install fake providers with short retry delays."""

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


def completed_payload(response_text: str) -> dict:
    """Extract the completed response JSON from an SSE body."""

    for block in response_text.split("\n\n"):
        lines = block.splitlines()

        if not lines or lines[0] != "event: completed":
            continue

        for line in lines[1:]:
            if line.startswith("data: "):
                return json.loads(line[6:])

    raise AssertionError(
        "Completed event was not present in the response."
    )


def test_stream_returns_deltas_and_completed_response(
    client,
    monkeypatch,
):
    primary = FakeStreamingProvider(
        [["Electricity ", "tariffs ", "use consumption slabs."]],
        model="gemini-3.5-flash-lite",
    )

    override_stream_dependencies(
        monkeypatch,
        primary,
    )

    response = client.post(
        "/chat/stream",
        json={
            "message": "Explain electricity tariff slabs."
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )

    body = response.text

    assert "event: delta" in body
    assert '"text": "Electricity "' in body
    assert '"text": "tariffs "' in body
    assert "event: completed" in body
    assert "event: done" in body

    completed = completed_payload(body)

    assert completed["answer"] == (
        "Electricity tariffs use consumption slabs."
    )
    assert completed["model"] == "gemini-3.5-flash-lite"
    assert completed["fallback_used"] is False
    assert completed["usage"]["total_tokens"] == 45

    assert primary.calls == 1


def test_stream_uses_fallback_when_primary_fails_before_first_token(
    client,
    monkeypatch,
):
    primary = FakeStreamingProvider(
        [
            [FakeProviderError(503)],
            [FakeProviderError(503)],
        ],
        model="primary-model",
    )

    fallback = FakeStreamingProvider(
        [["Fallback ", "model response."]],
        model="fallback-model",
    )

    override_stream_dependencies(
        monkeypatch,
        primary,
        fallback,
    )

    response = client.post(
        "/chat/stream",
        json={
            "message": "Explain tariff slabs."
        },
    )

    assert response.status_code == 200

    body = response.text
    completed = completed_payload(body)

    assert primary.calls == 2
    assert fallback.calls == 1

    # The final answer must come from the fallback provider.
    assert completed["answer"] == (
        "Fallback model response."
    )
    assert completed["model"] == "fallback-model"
    assert completed["fallback_used"] is True


def test_stream_does_not_restart_after_first_delta(
    client,
    monkeypatch,
):
    primary = FakeStreamingProvider(
        [
            [
                "Partial response",
                FakeProviderError(503),
            ]
        ],
        model="primary-model",
    )

    fallback = FakeStreamingProvider(
        [["This should never be used."]],
        model="fallback-model",
    )

    override_stream_dependencies(
        monkeypatch,
        primary,
        fallback,
    )

    response = client.post(
        "/chat/stream",
        json={
            "message": "Explain tariff slabs."
        },
    )

    assert response.status_code == 200

    body = response.text

    assert "Partial response" in body
    assert "event: error" in body
    assert "event: completed" not in body

    assert primary.calls == 1
    assert fallback.calls == 0


def test_stream_rejects_invalid_request_before_provider_lookup(
    client,
):
    response = client.post(
        "/chat/stream",
        json={
            "message": "   "
        },
    )

    assert response.status_code == 422
