import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from src.models import MarketEvent, MarketSource

logger = logging.getLogger(__name__)


class MarketStorage:
    """SQLite-based storage for tracking seen market events."""

    def __init__(self, db_path: str = "data/seen_markets.db"):
        self.db_path = db_path
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self):
        """Ensure the database directory exists."""
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_markets (
                    id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    category TEXT,
                    first_seen_at TEXT NOT NULL,
                    PRIMARY KEY (id, source)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_first_seen_at
                ON seen_markets (first_seen_at)
            """)
        logger.info(f"Database initialized at {self.db_path}")

    def is_seen(self, event: MarketEvent) -> bool:
        """Check if a market event has already been seen."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM seen_markets WHERE id = ? AND source = ?",
                (event.id, event.source.value),
            )
            return cursor.fetchone() is not None

    def mark_seen(self, event: MarketEvent):
        """Mark a market event as seen."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_markets
                (id, source, title, url, category, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.source.value,
                    event.title,
                    event.url,
                    event.category,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_new_events(self, events: list[MarketEvent]) -> list[MarketEvent]:
        """Filter a list of events to only include new (unseen) ones."""
        new_events = []
        for event in events:
            if not self.is_seen(event):
                new_events.append(event)
        return new_events

    def mark_many_seen(self, events: list[MarketEvent]):
        """Mark multiple events as seen in a single transaction."""
        with self._get_connection() as conn:
            for event in events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO seen_markets
                    (id, source, title, url, category, first_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.source.value,
                        event.title,
                        event.url,
                        event.category,
                        datetime.utcnow().isoformat(),
                    ),
                )

    def get_stats(self) -> dict:
        """Get statistics about seen markets."""
        with self._get_connection() as conn:
            stats = {}

            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM seen_markets")
            stats["total"] = cursor.fetchone()[0]

            # Count by source
            cursor = conn.execute(
                "SELECT source, COUNT(*) FROM seen_markets GROUP BY source"
            )
            stats["by_source"] = {row["source"]: row[1] for row in cursor.fetchall()}

            return stats

    def cleanup_old_entries(self, days: int = 90):
        """Remove entries older than the specified number of days."""
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM seen_markets WHERE first_seen_at < ?", (cutoff,)
            )
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old market entries")
