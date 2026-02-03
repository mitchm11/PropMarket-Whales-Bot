from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MarketSource(Enum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


@dataclass
class MarketEvent:
    """Unified market event representation from any source."""

    id: str
    source: MarketSource
    title: str
    description: str
    url: str
    category: str
    created_at: datetime | None = None
    end_date: datetime | None = None

    def __hash__(self):
        return hash((self.id, self.source))

    def __eq__(self, other):
        if not isinstance(other, MarketEvent):
            return False
        return self.id == other.id and self.source == other.source
