
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError

from app.usage.database import Database

metadata = MetaData()


usage_records_table = Table(
    "usage_records",
    metadata,
    Column("request_id", String(36), primary_key=True),
    Column("created_at", String(40), nullable=False),
    Column("model", String(150), nullable=False),

    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("thought_tokens", Integer, nullable=False),
    Column("tool_use_tokens", Integer, nullable=False),
    Column("cached_tokens", Integer, nullable=False),
    Column("total_tokens", Integer, nullable=False),

    Column("fallback_used", Integer, nullable=False),

    Column("pricing_tier", String(50), nullable=False),
    Column("input_price_usd_per_million", Text),
    Column("output_price_usd_per_million", Text),
    Column("cached_input_price_usd_per_million", Text),

    Column("estimated_cost_usd", Text),
    Column("cost_estimate_complete", Integer, nullable=False),
    Column("cost_estimate_note", Text),
)

Index(
    "idx_usage_records_created_at",
    usage_records_table.c.created_at,
)

Index(
    "idx_usage_records_model",
    usage_records_table.c.model,
)


@dataclass(frozen=True, slots=True)
class UsageRecord:
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
    input_price_usd_per_million: Decimal | None
    output_price_usd_per_million: Decimal | None
    cached_input_price_usd_per_million: Decimal | None

    estimated_cost_usd: Decimal | None
    cost_estimate_complete: bool
    cost_estimate_note: str | None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return format(value, ".12f")


def _money_total(values: list[str | None]) -> Decimal:
    total = Decimal("0")

    for value in values:
        if value is not None:
            total += Decimal(value)

    return total


def _money_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001")), "f")


class UsageRepository:
    """Database-independent SQLAlchemy usage repository."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        """Create the usage table and indexes if necessary."""

        metadata.create_all(self.database.engine)

        # Retain WAL mode for local SQLite databases.
        if self.database.engine.dialect.name == "sqlite":
            with self.database.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA journal_mode=WAL")

    def insert_record(self, record: UsageRecord) -> bool:
        """Insert a usage record, preventing duplicate request IDs."""

        values = {
            "request_id": record.request_id,
            "created_at": record.created_at,
            "model": record.model,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "thought_tokens": record.thought_tokens,
            "tool_use_tokens": record.tool_use_tokens,
            "cached_tokens": record.cached_tokens,
            "total_tokens": record.total_tokens,
            "fallback_used": int(record.fallback_used),
            "pricing_tier": record.pricing_tier,
            "input_price_usd_per_million": _decimal_text(
                record.input_price_usd_per_million
            ),
            "output_price_usd_per_million": _decimal_text(
                record.output_price_usd_per_million
            ),
            "cached_input_price_usd_per_million": _decimal_text(
                record.cached_input_price_usd_per_million
            ),
            "estimated_cost_usd": _decimal_text(
                record.estimated_cost_usd
            ),
            "cost_estimate_complete": int(
                record.cost_estimate_complete
            ),
            "cost_estimate_note": record.cost_estimate_note,
        }

        try:
            with self.database.engine.begin() as connection:
                existing = connection.execute(
                    select(usage_records_table.c.request_id).where(
                        usage_records_table.c.request_id
                        == record.request_id
                    )
                ).first()

                if existing is not None:
                    return False

                connection.execute(
                    insert(usage_records_table).values(**values)
                )

            return True

        except IntegrityError:
            # Another concurrent request may have inserted this ID.
            return False

    def get_snapshot(self, recent_limit: int = 20) -> dict[str, Any]:
        """Return aggregate usage, model summaries and recent records."""

        if not 1 <= recent_limit <= 100:
            raise ValueError(
                "recent_limit must be between 1 and 100."
            )

        with self.database.engine.connect() as connection:
            totals = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS request_count,
                        COALESCE(SUM(fallback_used), 0)
                            AS fallback_request_count,
                        COALESCE(SUM(input_tokens), 0)
                            AS input_tokens,
                        COALESCE(SUM(output_tokens), 0)
                            AS output_tokens,
                        COALESCE(SUM(thought_tokens), 0)
                            AS thought_tokens,
                        COALESCE(SUM(tool_use_tokens), 0)
                            AS tool_use_tokens,
                        COALESCE(SUM(cached_tokens), 0)
                            AS cached_tokens,
                        COALESCE(SUM(total_tokens), 0)
                            AS reported_total_tokens,
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN cost_estimate_complete = 0
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS unpriced_request_count
                    FROM usage_records
                    """
                )
            ).mappings().one()

            model_rows = connection.execute(
                text(
                    """
                    SELECT
                        model,
                        COUNT(*) AS request_count,
                        COALESCE(SUM(fallback_used), 0)
                            AS fallback_request_count,
                        COALESCE(SUM(input_tokens), 0)
                            AS input_tokens,
                        COALESCE(SUM(output_tokens), 0)
                            AS output_tokens,
                        COALESCE(SUM(thought_tokens), 0)
                            AS thought_tokens,
                        COALESCE(SUM(tool_use_tokens), 0)
                            AS tool_use_tokens,
                        COALESCE(SUM(cached_tokens), 0)
                            AS cached_tokens,
                        COALESCE(SUM(total_tokens), 0)
                            AS reported_total_tokens
                    FROM usage_records
                    GROUP BY model
                    ORDER BY request_count DESC, model ASC
                    """
                )
            ).mappings().all()

            cost_rows = connection.execute(
                text(
                    """
                    SELECT
                        model,
                        pricing_tier,
                        estimated_cost_usd,
                        cost_estimate_complete
                    FROM usage_records
                    """
                )
            ).mappings().all()

            recent_rows = connection.execute(
                text(
                    """
                    SELECT
                        request_id,
                        created_at,
                        model,
                        input_tokens,
                        output_tokens,
                        thought_tokens,
                        tool_use_tokens,
                        cached_tokens,
                        total_tokens,
                        fallback_used,
                        pricing_tier,
                        estimated_cost_usd,
                        cost_estimate_complete,
                        cost_estimate_note
                    FROM usage_records
                    ORDER BY created_at DESC, request_id DESC
                    LIMIT :recent_limit
                    """
                ),
                {"recent_limit": recent_limit},
            ).mappings().all()

        all_costs: list[str | None] = []
        unpriced_total = 0
        tiers: set[str] = set()

        model_costs: dict[str, list[str | None]] = {}
        model_unpriced: dict[str, int] = {}
        model_tiers: dict[str, set[str]] = {}

        for row in cost_rows:
            model = row["model"]
            tier = row["pricing_tier"]
            cost = row["estimated_cost_usd"]

            tiers.add(tier)
            all_costs.append(cost)

            model_costs.setdefault(model, []).append(cost)
            model_tiers.setdefault(model, set()).add(tier)

            if not row["cost_estimate_complete"]:
                unpriced_total += 1
                model_unpriced[model] = (
                    model_unpriced.get(model, 0) + 1
                )

        known_total = _money_total(all_costs)
        total_complete = unpriced_total == 0

        summary = {
            "request_count": totals["request_count"],
            "fallback_request_count": totals[
                "fallback_request_count"
            ],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "thought_tokens": totals["thought_tokens"],
            "tool_use_tokens": totals["tool_use_tokens"],
            "cached_tokens": totals["cached_tokens"],
            "reported_total_tokens": totals[
                "reported_total_tokens"
            ],
            "estimated_cost_usd": (
                _money_text(known_total)
                if total_complete
                else None
            ),
            "known_priced_cost_usd": _money_text(known_total),
            "unpriced_request_count": unpriced_total,
            "cost_estimate_complete": total_complete,
            "currency": "USD",
            "pricing_tiers": sorted(tiers),
        }

        models = []

        for row in model_rows:
            model = row["model"]
            known_model_cost = _money_total(
                model_costs.get(model, [])
            )
            model_unpriced_count = model_unpriced.get(model, 0)
            model_complete = model_unpriced_count == 0

            models.append(
                {
                    "model": model,
                    "request_count": row["request_count"],
                    "fallback_request_count": row[
                        "fallback_request_count"
                    ],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "thought_tokens": row["thought_tokens"],
                    "tool_use_tokens": row["tool_use_tokens"],
                    "cached_tokens": row["cached_tokens"],
                    "reported_total_tokens": row[
                        "reported_total_tokens"
                    ],
                    "estimated_cost_usd": (
                        _money_text(known_model_cost)
                        if model_complete
                        else None
                    ),
                    "known_priced_cost_usd": _money_text(
                        known_model_cost
                    ),
                    "unpriced_request_count": model_unpriced_count,
                    "cost_estimate_complete": model_complete,
                    "pricing_tiers": sorted(
                        model_tiers.get(model, set())
                    ),
                }
            )

        recent_requests = [
            {
                "request_id": row["request_id"],
                "created_at": row["created_at"],
                "model": row["model"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "thought_tokens": row["thought_tokens"],
                "tool_use_tokens": row["tool_use_tokens"],
                "cached_tokens": row["cached_tokens"],
                "total_tokens": row["total_tokens"],
                "fallback_used": bool(row["fallback_used"]),
                "pricing_tier": row["pricing_tier"],
                "estimated_cost_usd": row[
                    "estimated_cost_usd"
                ],
                "cost_estimate_complete": bool(
                    row["cost_estimate_complete"]
                ),
                "cost_estimate_note": row[
                    "cost_estimate_note"
                ],
            }
            for row in recent_rows
        ]

        return {
            "summary": summary,
            "models": models,
            "recent_requests": recent_requests,
        }


class SQLiteUsageRepository(UsageRepository):
    """Compatibility wrapper for existing local SQLite callers."""

    def __init__(self, database_path: str) -> None:
        database = Database.from_sqlite_path(database_path)
        super().__init__(database)
