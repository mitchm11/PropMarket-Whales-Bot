# PropMarket Whales Bot

A Discord bot that monitors Polymarket and Kalshi for new prediction market events and announces them via webhook.

## Features

- Monitors both Polymarket and Kalshi public APIs
- Posts new market events to Discord with rich embeds
- SQLite storage to track seen markets (no duplicate posts)
- Rate limit handling for both APIs and Discord
- Automatic retry with exponential backoff
- Graceful shutdown handling
- Initial sync to avoid spamming on first run

## Setup

### 1. Create a Discord Webhook

1. Go to your Discord server settings
2. Navigate to Integrations → Webhooks
3. Click "New Webhook"
4. Copy the webhook URL

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and set your webhook URL:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook-id/your-webhook-token
```

### 3. Run Locally

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

### 4. Deploy to Railway

1. Push this repo to GitHub
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repo
4. Add the `DISCORD_WEBHOOK_URL` environment variable
5. Deploy!

Railway will automatically detect the Dockerfile and run the bot.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_WEBHOOK_URL` | Yes | - | Discord webhook URL |
| `POLL_INTERVAL_SECONDS` | No | 300 | How often to check for new markets (in seconds) |
| `DATABASE_PATH` | No | data/seen_markets.db | Path to SQLite database |
| `BOT_USERNAME` | No | Market Events | Bot display name in Discord |
| `BOT_AVATAR_URL` | No | (default image) | Bot avatar URL |

## Architecture

```
[Poll APIs every X minutes] → [Compare to SQLite storage] → [Post new ones to Discord]
```

### Data Sources

- **Polymarket**: `https://gamma-api.polymarket.com/events` (no auth)
- **Kalshi**: `https://api.elections.kalshi.com/trade-api/v2/events` (no auth)

Both APIs are free for read-only access. Main risk is rate limiting, not billing.

## Project Structure

```
├── bot.py              # Main entry point
├── src/
│   ├── api_clients.py  # Polymarket & Kalshi API clients
│   ├── config.py       # Configuration management
│   ├── discord.py      # Discord webhook posting
│   ├── models.py       # Data models
│   └── storage.py      # SQLite storage
├── Dockerfile          # Container deployment
├── requirements.txt    # Python dependencies
└── .env.example        # Environment template
```

## Notes

- On first run, the bot syncs existing markets without posting (to avoid spam)
- Old market entries are automatically cleaned up after 90 days
- The bot handles graceful shutdown on SIGINT/SIGTERM
