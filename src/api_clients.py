import logging
from abc import ABC, abstractmethod
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.models import MarketEvent, MarketSource

logger = logging.getLogger(__name__)


def create_session_with_retries(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class MarketAPIClient(ABC):
    """Abstract base class for market API clients."""

    @abstractmethod
    def fetch_events(self) -> list[MarketEvent]:
        """Fetch all current events from the API."""
        pass


class PolymarketClient(MarketAPIClient):
    """Client for the Polymarket API."""

    def __init__(self, api_url: str = "https://gamma-api.polymarket.com/events"):
        self.api_url = api_url
        self.session = create_session_with_retries()

    def fetch_events(self) -> list[MarketEvent]:
        """Fetch active events from Polymarket."""
        events = []
        offset = 0
        limit = 100

        try:
            while True:
                response = self.session.get(
                    self.api_url,
                    params={
                        "active": "true",
                        "limit": limit,
                        "offset": offset,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for item in data:
                    event = self._parse_event(item)
                    if event:
                        events.append(event)

                if len(data) < limit:
                    break

                offset += limit

            logger.info(f"Fetched {len(events)} events from Polymarket")

        except requests.RequestException as e:
            logger.error(f"Error fetching from Polymarket: {e}")

        return events

    def _parse_event(self, data: dict) -> MarketEvent | None:
        """Parse a Polymarket event into our unified model."""
        try:
            event_id = data.get("id")
            if not event_id:
                return None

            # Build the URL from slug
            slug = data.get("slug", "")
            url = f"https://polymarket.com/event/{slug}" if slug else ""

            # Parse creation date
            created_at = None
            if creation_date := data.get("creationDate"):
                try:
                    created_at = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            return MarketEvent(
                id=str(event_id),
                source=MarketSource.POLYMARKET,
                title=data.get("title", "Unknown"),
                description=data.get("description", "")[:500],  # Truncate long descriptions
                url=url,
                category=data.get("category", "Unknown"),
                created_at=created_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Polymarket event: {e}")
            return None


class KalshiClient(MarketAPIClient):
    """Client for the Kalshi API."""

    def __init__(self, api_url: str = "https://api.elections.kalshi.com/trade-api/v2/events"):
        self.api_url = api_url
        self.session = create_session_with_retries()

    def fetch_events(self) -> list[MarketEvent]:
        """Fetch events from Kalshi."""
        events = []
        cursor = None

        try:
            while True:
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                response = self.session.get(
                    self.api_url,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                event_list = data.get("events", [])
                for item in event_list:
                    event = self._parse_event(item)
                    if event:
                        events.append(event)

                # Handle pagination
                cursor = data.get("cursor")
                if not cursor or not event_list:
                    break

            logger.info(f"Fetched {len(events)} events from Kalshi")

        except requests.RequestException as e:
            logger.error(f"Error fetching from Kalshi: {e}")

        return events

    def _parse_event(self, data: dict) -> MarketEvent | None:
        """Parse a Kalshi event into our unified model."""
        try:
            event_ticker = data.get("event_ticker")
            if not event_ticker:
                return None

            # Build URL from event ticker
            url = f"https://kalshi.com/markets/{event_ticker}"

            # Combine title and subtitle
            title = data.get("title", "Unknown")
            subtitle = data.get("sub_title", "")
            if subtitle:
                title = f"{title} - {subtitle}"

            return MarketEvent(
                id=event_ticker,
                source=MarketSource.KALSHI,
                title=title,
                description="",  # Kalshi doesn't provide description in list endpoint
                url=url,
                category=data.get("category", "Unknown"),
                created_at=None,  # Not provided in the response
            )
        except Exception as e:
            logger.warning(f"Failed to parse Kalshi event: {e}")
            return None
