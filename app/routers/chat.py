import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.llm.gemini_client import GeminiProvider
from app.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def get_gemini_provider(request: Request) -> GeminiProvider | None:
    """Retrieve the primary Gemini provider, if configured."""

    return getattr(request.app.state, "gemini_provider", None)


def get_gemini_fallback_provider(
    request: Request,
) -> GeminiProvider | None:
    """Retrieve the optional fallback Gemini provider."""

    return getattr(
        request.app.state,
        "gemini_fallback_provider",
        None,
    )


def encode_sse(event_type: str, payload: dict) -> str:
    """Encode one Server-Sent Event."""

    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


async def record_usage(
    request: Request,
    response: ChatResponse,
) -> None:
    """Persist usage without blocking the event loop."""

    usage_service = getattr(
        request.app.state,
        "usage_service",
        None,
    )

    if usage_service is None:
        return

    try:
        await asyncio.to_thread(
            usage_service.record_chat,
            response,
        )

    except Exception:
        logger.exception(
            "Failed to persist usage for request_id=%s",
            response.request_id,
        )


def create_chat_service(
    settings: Settings,
    provider: GeminiProvider,
    fallback_provider: GeminiProvider | None,
) -> ChatService:
    """Create a configured ChatService instance."""

    return ChatService(
        provider=provider,
        fallback_provider=fallback_provider,
        max_retries=settings.gemini_max_retries,
        retry_initial_delay_seconds=(
            settings.gemini_retry_initial_delay_seconds
        ),
        retry_max_delay_seconds=(
            settings.gemini_retry_max_delay_seconds
        ),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[
        GeminiProvider | None,
        Depends(get_gemini_provider),
    ],
    fallback_provider: Annotated[
        GeminiProvider | None,
        Depends(get_gemini_fallback_provider),
    ],
) -> ChatResponse:
    """Accept a message, generate a response and record its usage."""

    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini provider is not configured.",
        )

    service = create_chat_service(
        settings=settings,
        provider=provider,
        fallback_provider=fallback_provider,
    )

    try:
        response = await service.generate_reply(payload.message)

    except Exception as exc:
        logger.exception("Chat generation failed")

        raise HTTPException(
            status_code=502,
            detail="The AI provider could not complete the request.",
        ) from exc

    await record_usage(request, response)

    return response


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[
        GeminiProvider | None,
        Depends(get_gemini_provider),
    ],
    fallback_provider: Annotated[
        GeminiProvider | None,
        Depends(get_gemini_fallback_provider),
    ],
) -> StreamingResponse:
    """Stream incremental Gemini text using Server-Sent Events."""

    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini provider is not configured.",
        )

    service = create_chat_service(
        settings=settings,
        provider=provider,
        fallback_provider=fallback_provider,
    )

    stream_events = service.stream_reply(payload.message)

    # Prefetch the first event so provider failures before streaming
    # starts can still return a normal HTTP error response.
    try:
        first_event = await anext(stream_events)

    except Exception as exc:
        await stream_events.aclose()

        logger.exception(
            "Chat streaming failed before the response started."
        )

        raise HTTPException(
            status_code=502,
            detail="The AI provider could not start the stream.",
        ) from exc

    async def event_body():
        """Convert ChatService events into SSE messages."""

        try:

            async def all_events():
                yield first_event

                async for stream_event in stream_events:
                    yield stream_event

            async for stream_event in all_events():

                if stream_event.event_type == "delta":
                    yield encode_sse(
                        "delta",
                        {
                            "text": stream_event.text or "",
                        },
                    )

                elif stream_event.event_type == "completed":
                    response = stream_event.response

                    if response is None:
                        continue

                    await record_usage(
                        request,
                        response,
                    )

                    yield encode_sse(
                        "completed",
                        response.model_dump(mode="json"),
                    )

            yield "event: done\ndata: [DONE]\n\n"

        except Exception:
            logger.exception(
                "Chat streaming failed after the response started."
            )

            yield encode_sse(
                "error",
                {
                    "detail": (
                        "The AI provider could not complete the stream."
                    )
                },
            )

        finally:
            await stream_events.aclose()

    return StreamingResponse(
        event_body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )