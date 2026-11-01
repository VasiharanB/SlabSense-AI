
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI

from app.config import Settings, get_settings
from app.llm.gemini_client import GeminiProvider
from app.routers.chat import router as chat_router
from app.routers.usage import router as usage_router
from app.usage.database import Database
from app.usage.pricing import UsagePricingCalculator
from app.usage.repository import UsageRepository
from app.usage.service import UsageService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up application services."""

    settings = get_settings()
    providers: list[GeminiProvider] = []
    database: Database | None = None

    app.state.gemini_provider = None
    app.state.gemini_fallback_provider = None
    app.state.usage_database = None
    app.state.usage_repository = None
    app.state.usage_service = None

    try:
        # 1. Select PostgreSQL URL or local SQLite.
        database_url = (
            settings.usage_database_url or ""
        ).strip()

        if database_url:
            database = Database(database_url)
            database_backend = "configured SQLAlchemy database"
        else:
            database = Database.from_sqlite_path(
                settings.usage_database_path
            )
            database_backend = "SQLite"

        # 2. Initialize usage storage.
        usage_repository = UsageRepository(database)
        usage_repository.initialize()

        # 3. Initialize pricing and usage services.
        pricing_calculator = UsagePricingCalculator(settings)

        usage_service = UsageService(
            repository=usage_repository,
            pricing_calculator=pricing_calculator,
        )

        app.state.usage_database = database
        app.state.usage_repository = usage_repository
        app.state.usage_service = usage_service

        logger.info(
            "Usage storage initialized. backend=%s pricing_tier=%s",
            database_backend,
            settings.usage_pricing_tier,
        )

        # 4. Initialize Gemini primary and optional fallback providers.
        if settings.gemini_api_key is not None:
            primary_provider = GeminiProvider.from_settings(settings)

            providers.append(primary_provider)
            app.state.gemini_provider = primary_provider

            fallback_model = (
                settings.gemini_fallback_model or ""
            ).strip()

            if fallback_model and fallback_model != settings.gemini_model:
                fallback_provider = GeminiProvider(
                    api_key=settings.gemini_api_key.get_secret_value(),
                    model=fallback_model,
                    timeout_seconds=settings.gemini_timeout_seconds,
                )

                providers.append(fallback_provider)
                app.state.gemini_fallback_provider = fallback_provider

            elif fallback_model:
                logger.warning(
                    "Fallback model matches primary model. "
                    "Fallback provider was not created."
                )

        yield

    finally:
        # 5. Clear application state.
        app.state.gemini_provider = None
        app.state.gemini_fallback_provider = None
        app.state.usage_database = None
        app.state.usage_repository = None
        app.state.usage_service = None

        # 6. Close Gemini clients.
        for provider in reversed(providers):
            try:
                await provider.aclose()
            except Exception:
                logger.exception(
                    "Failed to close Gemini client for model=%s",
                    provider.model,
                )

        # 7. Dispose database connections.
        if database is not None:
            try:
                database.dispose()
            except Exception:
                logger.exception("Failed to dispose database engine")


app = FastAPI(
    title="SlabSense API",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(chat_router)
app.include_router(usage_router)


SettingsDep = Annotated[
    Settings,
    Depends(get_settings),
]


@app.get("/health")
def health(settings: SettingsDep) -> dict:
    """Liveness check. Does not call the LLM or database."""

    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }
