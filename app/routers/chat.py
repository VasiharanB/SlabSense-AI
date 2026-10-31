
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.llm.gemini_client import GeminiProvider
from app.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def get_gemini_provider(request: Request) -> GeminiProvider:
    """Retrieve the primary Gemini provider."""

    provider = getattr(request.app.state, "gemini_provider", None)

    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini provider is not configured.",
        )

    return provider


def get_gemini_fallback_provider(
    request: Request,
) -> GeminiProvider | None:
    """Retrieve the optional fallback Gemini provider."""

    return getattr(
        request.app.state,
        "gemini_fallback_provider",
        None,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[
        GeminiProvider,
        Depends(get_gemini_provider),
    ],
    fallback_provider: Annotated[
        GeminiProvider | None,
        Depends(get_gemini_fallback_provider),
    ],
) -> ChatResponse:
    """Accept a message, generate a response and record its usage."""

    service = ChatService(
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

    try:
        response = await service.generate_reply(payload.message)

    except Exception as exc:
        logger.exception("Chat generation failed")

        raise HTTPException(
            status_code=502,
            detail="The AI provider could not complete the request.",
        ) from exc

    # Usage persistence must not turn a successful AI response
    # into a failed chat request.
    usage_service = getattr(
        request.app.state,
        "usage_service",
        None,
    )

    if usage_service is not None:
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

    return response
