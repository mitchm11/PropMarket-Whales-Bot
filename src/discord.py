import logging
import time
from collections import defaultdict

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

    def _format_grouped_embed(self, category: str, events: list[MarketEvent]) -> dict:
        """Format a group of events in the same category as a single Discord embed."""
        count = len(events)
        title = f"{count} New {category} Event{'s' if count != 1 else ''}"

        # Build list of event links with source icons
        lines = []
        for event in events:
            source_icon = self._get_source_icon(event.source)
            if event.url:
                lines.append(f"{source_icon} [{event.title}]({event.url})")
            else:
                lines.append(f"{source_icon} {event.title}")

        description = "\n".join(lines)
        # Truncate to Discord's 4096 char description limit
        if len(description) > 4096:
            description = description[:4093] + "..."

        # Use the color of the first event's source
        color = self._get_embed_color(events[0].source)

        # If mixed sources, use default blurple
        sources = {e.source for e in events}
        if len(sources) > 1:
            color = 0x5865F2

        return {
            "title": title,
            "description": description,
            "color": color,
        }

    def post_grouped_events(self, events: list[MarketEvent]) -> list[MarketEvent]:
        """Post events grouped by category. Returns the list of successfully posted events."""
        if not events:
            return []

        # Group events by category
        by_category: dict[str, list[MarketEvent]] = defaultdict(list)
        for event in events:
            by_category[event.category or "Unknown"].append(event)

        posted_events: list[MarketEvent] = []

        for category, group in by_category.items():
            if len(group) == 1:
                # Single event in category - post as individual compact embed
                embed = self._format_embed(group[0])
            else:
                # Multiple events - post as grouped summary
                embed = self._format_grouped_embed(category, group)

            self._respect_rate_limit()
            payload = {
                "username": self.config.bot_username,
                "avatar_url": self.config.bot_avatar_url,
                "embeds": [embed],
            }

            try:
                response = self.session.post(
                    self.config.discord_webhook_url,
                    json=payload,
                    timeout=10,
                )

                if response.status_code == 429:
                    retry_after = response.json().get("retry_after", 5)
                    logger.warning(f"Rate limited by Discord, waiting {retry_after}s")
                    time.sleep(retry_after)
                    # Retry this group
                    response = self.session.post(
                        self.config.discord_webhook_url,
                        json=payload,
                        timeout=10,
                    )

                response.raise_for_status()
                posted_events.extend(group)
                if len(group) == 1:
                    logger.info(f"Posted event to Discord: {group[0].title[:50]}...")
                else:
                    logger.info(f"Posted {len(group)} {category} events to Discord as group")

            except requests.RequestException as e:
                logger.error(f"Failed to post {category} group to Discord: {e}")

        return posted_events

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
