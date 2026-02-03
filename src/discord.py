import logging
import time

import requests

from src.config import Config
from src.models import MarketEvent, MarketSource

logger = logging.getLogger(__name__)


class DiscordWebhook:
    """Discord webhook client for posting market events."""

    # Discord rate limits: 30 requests per 60 seconds per webhook
    RATE_LIMIT_DELAY = 2.0  # seconds between posts to be safe

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self._last_post_time = 0.0

    def _get_embed_color(self, source: MarketSource) -> int:
        """Get the embed color for a market source."""
        if source == MarketSource.POLYMARKET:
            return self.config.polymarket_color
        elif source == MarketSource.KALSHI:
            return self.config.kalshi_color
        return 0x5865F2  # Discord blurple default

    def _get_source_icon(self, source: MarketSource) -> str:
        """Get the icon/emoji for a market source."""
        if source == MarketSource.POLYMARKET:
            return "🟣"
        elif source == MarketSource.KALSHI:
            return "🟢"
        return "📊"

    def _format_embed(self, event: MarketEvent) -> dict:
        """Format a market event as a Discord embed."""
        source_icon = self._get_source_icon(event.source)
        source_name = event.source.value.title()

        embed = {
            "title": event.title[:256],  # Discord limit
            "url": event.url if event.url else None,
            "color": self._get_embed_color(event.source),
            "fields": [
                {
                    "name": "Source",
                    "value": f"{source_icon} {source_name}",
                    "inline": True,
                },
                {
                    "name": "Category",
                    "value": event.category or "Unknown",
                    "inline": True,
                },
            ],
            "footer": {
                "text": f"New {source_name} Event",
            },
        }

        # Add description if available
        if event.description:
            embed["description"] = event.description[:2048]  # Discord limit

        # Add timestamp if available
        if event.created_at:
            embed["timestamp"] = event.created_at.isoformat()

        return embed

    def _respect_rate_limit(self):
        """Ensure we don't exceed Discord's rate limits."""
        elapsed = time.time() - self._last_post_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_post_time = time.time()

    def post_event(self, event: MarketEvent) -> bool:
        """Post a single market event to Discord."""
        self._respect_rate_limit()

        payload = {
            "username": self.config.bot_username,
            "avatar_url": self.config.bot_avatar_url,
            "embeds": [self._format_embed(event)],
        }

        try:
            response = self.session.post(
                self.config.discord_webhook_url,
                json=payload,
                timeout=10,
            )

            if response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = response.json().get("retry_after", 5)
                logger.warning(f"Rate limited by Discord, waiting {retry_after}s")
                time.sleep(retry_after)
                return self.post_event(event)  # Retry

            response.raise_for_status()
            logger.info(f"Posted event to Discord: {event.title[:50]}...")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to post to Discord: {e}")
            return False

    def post_events(self, events: list[MarketEvent]) -> int:
        """Post multiple events to Discord. Returns count of successful posts."""
        successful = 0
        for event in events:
            if self.post_event(event):
                successful += 1
        return successful

    def post_startup_message(self) -> bool:
        """Post a startup notification to Discord."""
        # Format expiration filter
        hours = self.config.min_hours_to_expiration
        if hours >= 24:
            expiration_str = f"{hours // 24}+ days"
        else:
            expiration_str = f"{hours}+ hours"

        payload = {
            "username": self.config.bot_username,
            "avatar_url": self.config.bot_avatar_url,
            "embeds": [
                {
                    "title": "Market Events Bot Started",
                    "description": "Now monitoring Polymarket and Kalshi for new events.",
                    "color": 0x5865F2,
                    "fields": [
                        {
                            "name": "Poll Interval",
                            "value": f"{self.config.poll_interval_seconds // 60} minutes",
                            "inline": True,
                        },
                        {
                            "name": "Min Duration",
                            "value": expiration_str,
                            "inline": True,
                        },
                        {
                            "name": "Sources",
                            "value": "🟣 Polymarket\n🟢 Kalshi",
                            "inline": True,
                        },
                    ],
                }
            ],
        }

        try:
            response = self.session.post(
                self.config.discord_webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Posted startup message to Discord")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to post startup message: {e}")
            return False
