# Discord Stock Bot

A small self-hosted Discord slash-command bot for Heikin-Ashi stock charts, company info, and recent news.

## Commands

Each chart command returns a Heikin-Ashi candle chart and takes a ticker symbol, such as `AAPL`, `MSFT`, `TSLA`, `SPY`, or `BTC-USD`.

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

The easiest path on Unraid is to put this folder in an appdata directory, create the `.env` file, then run it with Docker Compose.

If you use the Unraid Compose Manager plugin:

1. Create a new stack.
2. Point it at this folder or paste the `docker-compose.yml`.
3. Add the `.env` file beside the compose file.
4. Build and start the stack.

The container does not need GPU access. Ollama is not used.

## Local non-Docker run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m stockbot.bot
```

## Data source

This bot uses Yahoo Finance data through `yfinance`. It is convenient for personal/friend-group bots, but it is not a paid market data feed and should not be treated as guaranteed real-time financial data.

This bot is for fun and convenience, not financial advice.
