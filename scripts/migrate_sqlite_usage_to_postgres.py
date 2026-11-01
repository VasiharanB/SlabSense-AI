
import sqlite3
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import URL

from app.config import get_settings
from app.usage.database import Database
from app.usage.repository import UsageRecord, UsageRepository


def to_decimal(value: str | None) -> Decimal | None:
    """Convert a SQLite numeric string into Decimal."""

    if value is None:
        return None

    return Decimal(str(value))


def build_postgres_url() -> URL:
    """Build the Windows-host PostgreSQL connection URL."""

    settings = get_settings()

    if settings.postgres_password is None:
        raise RuntimeError(
            "POSTGRES_PASSWORD is not configured in .env."
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def migrate() -> None:
    """Copy historical SQLite usage records into PostgreSQL."""

    settings = get_settings()

    source_path = Path(
        settings.usage_database_path
    ).expanduser().resolve()

    if not source_path.is_file():
        raise FileNotFoundError(
            f"SQLite database was not found: {source_path}"
        )

    required_columns = {
        "request_id",
        "created_at",
        "model",
        "input_tokens",
        "output_tokens",
        "thought_tokens",
        "tool_use_tokens",
        "cached_tokens",
        "total_tokens",
        "fallback_used",
        "pricing_tier",
        "input_price_usd_per_million",
        "output_price_usd_per_million",
        "cached_input_price_usd_per_million",
        "estimated_cost_usd",
        "cost_estimate_complete",
        "cost_estimate_note",
    }

    # Construct the PostgreSQL database engine.
    target_database = Database(build_postgres_url())
    target_repository = UsageRepository(target_database)

    source_connection = None

    try:
        # Create the target table if it does not exist.
        target_repository.initialize()

        # Open SQLite in read-only mode.
        source_uri = f"{source_path.as_uri()}?mode=ro"

        source_connection = sqlite3.connect(
            source_uri,
            uri=True,
        )
        source_connection.row_factory = sqlite3.Row

        # Validate the SQLite schema.
        table = source_connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'usage_records'
            """
        ).fetchone()

        if table is None:
            raise RuntimeError(
                "The SQLite database does not contain usage_records."
            )

        actual_columns = {
            row["name"]
            for row in source_connection.execute(
                "PRAGMA table_info(usage_records)"
            ).fetchall()
        }

        missing_columns = required_columns - actual_columns

        if missing_columns:
            raise RuntimeError(
                "The SQLite usage table is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        rows = source_connection.execute(
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
                input_price_usd_per_million,
                output_price_usd_per_million,
                cached_input_price_usd_per_million,
                estimated_cost_usd,
                cost_estimate_complete,
                cost_estimate_note
            FROM usage_records
            ORDER BY created_at ASC, request_id ASC
            """
        ).fetchall()

        total_source_records = len(rows)
        migrated_records = 0
        skipped_records = 0

        print("========== SQLITE MIGRATION ==========")
        print("Source:", source_path)
        print("Target:", settings.postgres_host)
        print("Target database:", settings.postgres_db)
        print("Source records:", total_source_records)
        print("--------------------------------------")

        for row in rows:
            record = UsageRecord(
                request_id=row["request_id"],
                created_at=row["created_at"],
                model=row["model"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                thought_tokens=row["thought_tokens"],
                tool_use_tokens=row["tool_use_tokens"],
                cached_tokens=row["cached_tokens"],
                total_tokens=row["total_tokens"],
                fallback_used=bool(row["fallback_used"]),
                pricing_tier=row["pricing_tier"],
                input_price_usd_per_million=to_decimal(
                    row["input_price_usd_per_million"]
                ),
                output_price_usd_per_million=to_decimal(
                    row["output_price_usd_per_million"]
                ),
                cached_input_price_usd_per_million=to_decimal(
                    row["cached_input_price_usd_per_million"]
                ),
                estimated_cost_usd=to_decimal(
                    row["estimated_cost_usd"]
                ),
                cost_estimate_complete=bool(
                    row["cost_estimate_complete"]
                ),
                cost_estimate_note=row["cost_estimate_note"],
            )

            inserted = target_repository.insert_record(record)

            if inserted:
                migrated_records += 1
            else:
                skipped_records += 1

        target_snapshot = target_repository.get_snapshot(
            recent_limit=1
        )

        print("Migrated records:", migrated_records)
        print("Skipped existing records:", skipped_records)
        print(
            "PostgreSQL total records:",
            target_snapshot["summary"]["request_count"],
        )
        print("======================================")

        print("PASS: SQLite migration completed.")

    finally:
        if source_connection is not None:
            source_connection.close()

        target_database.dispose()


if __name__ == "__main__":
    migrate()
