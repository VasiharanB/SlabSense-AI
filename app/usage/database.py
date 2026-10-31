
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine.base import Engine


class Database:
    """Shared SQLAlchemy database engine for SlabSense."""

    def __init__(self, database_url: str | URL) -> None:
        url = make_url(database_url)

        connect_args = {}

        if url.get_backend_name() == "sqlite":
            connect_args["check_same_thread"] = False

            # Ensure the SQLite database directory exists.
            if url.database and url.database != ":memory:":
                database_path = Path(url.database).expanduser()
                database_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        # Enable SQLite foreign-key enforcement.
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def enable_sqlite_foreign_keys(
                dbapi_connection,
                connection_record,
            ) -> None:
                cursor = dbapi_connection.cursor()

                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

    @classmethod
    def from_sqlite_path(cls, database_path: str) -> "Database":
        """Create a SQLAlchemy database from a local SQLite path."""

        path = Path(database_path).expanduser().resolve()

        url = URL.create(
            drivername="sqlite",
            database=str(path),
        )

        return cls(url)

    def dispose(self) -> None:
        """Close all pooled database connections."""

        self.engine.dispose()
