#!/usr/bin/env python3
"""
PropMarket Whales Bot - Discord bot for announcing new prediction market events.

Monitors Polymarket and Kalshi for new events and posts them to a Discord webhook.
"""

import logging
import signal
import sys
import time
from datetime import datetime

from src.api_clients import KalshiClient, PolymarketClient
from src.config import Config
from src.discord import DiscordWebhook
from src.models import MarketEvent
from src.storage import MarketStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class MarketEventsBot:
    """Main bot class that orchestrates market monitoring and Discord posting."""

    def __init__(self, config: Config):
        self.config = config
        self.storage = MarketStorage(config.database_path)
        self.discord = DiscordWebhook(config)
        self.polymarket = PolymarketClient(
            config.polymarket_api_url,
            min_hours_to_expiration=config.min_hours_to_expiration
        )
        self.kalshi = KalshiClient(
            config.kalshi_api_url,
            min_hours_to_expiration=config.min_hours_to_expiration
        )
        self._running = False

    def _fetch_all_events(self) -> list[MarketEvent]:
        """Fetch events from all sources."""
        all_events = []

        # Fetch from Polymarket
        try:
            polymarket_events = self.polymarket.fetch_events()
            all_events.extend(polymarket_events)
        except Exception as e:
            logger.error(f"Error fetching Polymarket events: {e}")

        # Fetch from Kalshi
        try:
            kalshi_events = self.kalshi.fetch_events()
            all_events.extend(kalshi_events)
        except Exception as e:
            logger.error(f"Error fetching Kalshi events: {e}")

        return all_events

    def _process_events(self, events: list[MarketEvent]) -> int:
        """Process events: filter new ones and post to Discord. Returns count posted."""
        new_events = self.storage.get_new_events(events)

        if not new_events:
            logger.info("No new events found")
            return 0

        logger.info(f"Found {len(new_events)} new events")

        # Post to Discord grouped by category
        posted_events = self.discord.post_grouped_events(new_events)
        for event in posted_events:
            self.storage.mark_seen(event)

        logger.info(f"Posted {len(posted_events)}/{len(new_events)} events to Discord")
        return len(posted_events)

    def run_once(self) -> int:
        """Run a single poll cycle. Returns number of events posted."""
        logger.info("Starting poll cycle...")
        events = self._fetch_all_events()
        logger.info(f"Fetched {len(events)} total events from all sources")
        return self._process_events(events)

    def run(self):
        """Run the bot in a continuous polling loop."""
        self._running = True
        logger.info(
            f"Starting bot with {self.config.poll_interval_seconds}s poll interval"
        )

        # Post startup message
        self.discord.post_startup_message()

        # Initial population of database without posting
        # (so we don't spam on first run)
        self._initial_sync()

        while self._running:
            try:
                self.run_once()

                # Periodic cleanup (once per day worth of cycles)
                cycles_per_day = 86400 // self.config.poll_interval_seconds
                if hasattr(self, "_cycle_count"):
                    self._cycle_count += 1
                else:
                    self._cycle_count = 1

                if self._cycle_count % cycles_per_day == 0:
                    self.storage.cleanup_old_entries(days=90)

            except Exception as e:
                logger.error(f"Error in poll cycle: {e}", exc_info=True)

            if self._running:
                logger.info(
                    f"Sleeping for {self.config.poll_interval_seconds}s until next poll"
                )
                time.sleep(self.config.poll_interval_seconds)

    def _initial_sync(self):
        """Initial sync to populate database without posting."""
        logger.info("Performing initial sync (marking existing events as seen)...")
        events = self._fetch_all_events()
        self.storage.mark_many_seen(events)
        stats = self.storage.get_stats()
        logger.info(f"Initial sync complete. Stats: {stats}")

    def stop(self):
        """Signal the bot to stop."""
        logger.info("Stopping bot...")
        self._running = False


def main():
    """Main entry point."""
    # Load configuration
    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Create and run bot
    bot = MarketEventsBot(config)

    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the bot
    bot.run()


if __name__ == "__main__":
    main()
