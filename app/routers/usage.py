
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.usage.schemas import UsageResponse
from app.usage.service import UsageService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["usage"])


def get_usage_service(request: Request) -> UsageService:
    """Retrieve the application usage service."""

    service = getattr(request.app.state, "usage_service", None)

    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Usage tracking is not initialized.",
        )

    return service


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    service: Annotated[
        UsageService,
        Depends(get_usage_service),
    ],
    recent_limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,
) -> UsageResponse:
    """Return usage totals, model breakdown and recent requests."""

    try:
        return await asyncio.to_thread(
            service.get_usage,
            recent_limit,
        )

    except Exception as exc:
        logger.exception("Failed to retrieve usage summary")

        raise HTTPException(
            status_code=503,
            detail="Usage information is temporarily unavailable.",
        ) from exc
