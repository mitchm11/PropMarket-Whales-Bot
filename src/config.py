import os
from dataclasses import dataclass


@dataclass
class Config:
    """Bot configuration loaded from environment variables."""

    discord_webhook_url: str
    poll_interval_seconds: int = 300  # 5 minutes default
    database_path: str = "data/seen_markets.db"

    # API endpoints
    polymarket_api_url: str = "https://gamma-api.polymarket.com/events"
    kalshi_api_url: str = "https://api.elections.kalshi.com/trade-api/v2/events"

    # Bot appearance
    bot_username: str = "Market Events"
    bot_avatar_url: str = "https://i.imgur.com/AfFp7pu.png"

    # Colors for embeds (as integers)
    polymarket_color: int = 0x7C3AED  # Purple
    kalshi_color: int = 0x10B981     # Green

    # Filtering
    min_hours_to_expiration: int = 24  # Only show markets with at least this many hours until expiration

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

        return cls(
            discord_webhook_url=webhook_url,
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
            database_path=os.getenv("DATABASE_PATH", "data/seen_markets.db"),
            bot_username=os.getenv("BOT_USERNAME", "Market Events"),
            bot_avatar_url=os.getenv("BOT_AVATAR_URL", "https://i.imgur.com/AfFp7pu.png"),
            min_hours_to_expiration=int(os.getenv("MIN_HOURS_TO_EXPIRATION", "24")),
        )
