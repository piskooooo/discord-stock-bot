# Discord Stock Bot

A small self-hosted Discord slash-command bot for Heikin-Ashi stock charts, company info, and recent news.

This bot is intended for private friend-group servers. It is for fun and convenience, not financial advice.

## Commands

Each chart command returns a Heikin-Ashi candle chart with volume and takes a ticker symbol, such as `AAPL`, `MSFT`, `TSLA`, `SPY`, or `BTC-USD`.

| Command | Range |
| --- | --- |
| `/mi` | 5-minute candles for the current trading day |
| `/da` | 1-day chart |
| `/we` | 1-week chart |
| `/mo` | 1-month chart |
| `/ytd` | Year to date |
| `/y1` | 1 year |
| `/y5` | 5 years |
| `/all` | All available history |
| `/info` | Basic company and quote information |
| `/news` | Recent stock news |

## Create the Discord bot

1. Go to the Discord Developer Portal.
2. Create an application, then create a bot for it.
3. Copy the bot token.
4. In OAuth2 > URL Generator, select:
   - `bot`
   - `applications.commands`
5. Under Bot Permissions, select at least:
   - `Send Messages`
   - `Embed Links`
   - `Attach Files`
6. Open the generated invite URL and add the bot to your server.

## Configure

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your_real_token_here
DISCORD_GUILD_ID=your_server_id_optional
LOG_LEVEL=INFO
```

`DISCORD_GUILD_ID` is optional but useful. Guild commands usually update quickly, while global slash commands can take longer to appear.

## Run with Docker Compose

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## Unraid notes

The production image is published to:

```text
ghcr.io/piskooooo/discord-stock-bot:latest
```

Create a normal Unraid Docker container with that repository and add these variables:

- `DISCORD_TOKEN`: required bot token.
- `DISCORD_GUILD_ID`: optional private server ID for fast command updates.
- `LOG_LEVEL`: optional; defaults to `INFO`.

After a new image is published, force an update or pull the latest image and restart the container. Docker Compose remains available for local development from a checked-out copy of the repository.

The container does not need storage mounts, GPU access, Redis, a database, or Ollama.

## Local non-Docker run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m stockbot.bot
```

## Tests

```bash
python3 -m py_compile stockbot/bot.py stockbot/market_data.py
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks before publishing a Docker image.

## Data source

This bot uses Yahoo Finance chart, quote, profile, and RSS news sources. Some quote/profile enrichment uses `yfinance` as a best-effort fallback. These sources are convenient for personal/friend-group bots, but they are not a paid market data feed and should not be treated as guaranteed real-time financial data.

This bot is for fun and convenience, not financial advice.

## Policy notes

- See [PRIVACY.md](PRIVACY.md) for the bot's basic privacy policy.
- See [TERMS.md](TERMS.md) for usage terms and disclaimers.
- See [docs/compliance.md](docs/compliance.md) for the deployment compliance checklist.
