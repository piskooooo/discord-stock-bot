# Discord Stock Bot Handoff

## Product Goal And Status

The project is a self-hosted Discord slash-command bot for a small friend-group chat. It pulls stock charts, recent news, and basic ticker/company info. It is currently working in production on Unraid using the public GHCR image:

```text
ghcr.io/piskooooo/discord-stock-bot:latest
```

The public GitHub repository is:

```text
https://github.com/piskooooo/discord-stock-bot
```

Current commands:

- `/mi SYMBOL`: 5-minute Heikin-Ashi candles for the current trading day.
- `/da SYMBOL`: 1-day chart.
- `/we SYMBOL`: 1-week chart.
- `/mo SYMBOL`: 1-month chart.
- `/ytd SYMBOL`: year-to-date chart.
- `/y1 SYMBOL`: 1-year chart.
- `/y5 SYMBOL`: 5-year chart.
- `/all SYMBOL`: all available history.
- `/info SYMBOL`: basic quote/company info.
- `/news SYMBOL`: recent news.

Charts are dark-mode PNGs with Heikin-Ashi candles, volume, right-side price/volume axes, and Yahoo Finance data. `/mi` is special: it uses 5-minute candles, filters display data to regular market hours, shows the full 9:30 AM-4:00 PM Eastern session even if the day is not over, and uses fixed readable x-axis ticks.

## Repo Structure

```text
.
├── .dockerignore
├── .env.example
├── .github/workflows/docker-image.yml
├── .gitignore
├── AGENTS.md
├── Dockerfile
├── README.md
├── docker-compose.yml
├── docs/handoff.md
├── requirements.txt
└── stockbot
    ├── __init__.py
    ├── bot.py
    └── market_data.py
```

`stockbot/bot.py` owns Discord client setup, slash command registration, embeds, and user-facing command behavior.

`stockbot/market_data.py` owns ticker cleanup, Yahoo Finance calls, chart range definitions, Heikin-Ashi calculation, chart rendering, volume rendering, `/info` data, news parsing, and money formatting.

`.github/workflows/docker-image.yml` builds and publishes the public Docker image to GHCR on every push to `main`.

## Setup, Run, And Test Commands

Local setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m stockbot.bot
```

Required environment:

```env
DISCORD_TOKEN=your_real_token_here
DISCORD_GUILD_ID=your_server_id_optional
LOG_LEVEL=INFO
```

Syntax smoke test:

```bash
python3 -m py_compile stockbot/bot.py stockbot/market_data.py
```

Docker Compose:

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

GitHub Actions image checks:

```bash
gh run list --repo piskooooo/discord-stock-bot --limit 3
gh run watch RUN_ID --repo piskooooo/discord-stock-bot --exit-status
```

Normal update flow after code changes:

```bash
git status --short --branch
python3 -m py_compile stockbot/bot.py stockbot/market_data.py
git add .
git commit -m "Concise change summary"
git push
gh run list --repo piskooooo/discord-stock-bot --limit 1
gh run watch RUN_ID --repo piskooooo/discord-stock-bot --exit-status
```

After the image builds, the user updates the Unraid Docker container by pulling `ghcr.io/piskooooo/discord-stock-bot:latest` and restarting it.

## Key Architecture Decisions

- Python was chosen to keep the bot small and easy to self-host.
- `discord.py` handles slash commands and Discord embeds.
- Chart generation uses `matplotlib` with the non-interactive `Agg` backend.
- Charts are rendered server-side as PNG attachments, which keeps the Discord UX simple.
- Yahoo Finance direct HTTP endpoints are used for charts, quote basics, search profile fallback, and RSS news. This replaced the original `yfinance.Ticker.history()` chart path because yfinance hit rate limits.
- `yfinance` remains only as a best-effort richer profile source for `/info`; it frequently returns incomplete data or can be blocked.
- `/info` intentionally degrades gracefully to basic quote/search data if richer Yahoo profile data fails.
- GHCR publishing is automated with GitHub Actions. The repo and package are public so Unraid can pull without auth.
- Secrets are not stored in the repo or image. They live in Unraid environment variables.

## Open Tasks

- Add real automated tests around Heikin-Ashi calculations, chart range handling, Yahoo response parsing, and `/info` fallback behavior.
- Consider adding command usage logging for future weekly summaries.
- Consider a `/weekly` command that summarizes broad market movement plus tickers discussed in the Discord group that week.
- Consider lightweight caching to reduce Yahoo calls and avoid rate limits.
- Improve `/info` richness if a more stable no-key data source is chosen.
- Update README wording around data source details. It still mentions `yfinance` broadly, while the current chart/news path mostly uses direct Yahoo endpoints with `yfinance` as a fallback.

## Known Bugs And Fragile Areas

- Yahoo Finance endpoints are unofficial and can return `401`, `429`, empty data, or changed schemas.
- `/news` uses Yahoo RSS and may have sparse or inconsistent publisher/date data.
- `/info` can show `n/a` for market cap or summary because the richer profile endpoint is unreliable.
- No automated tests exist yet; current verification is `py_compile`, manual Discord testing, and GitHub Actions Docker build success.
- Slash command sync runs on startup. If `DISCORD_GUILD_ID` is set, commands sync quickly to that guild; global commands can take much longer.
- The public GHCR image must remain public for simple Unraid pulls without registry login.
- `docker-compose.yml` includes a bind mount for local development/Dockge-style workflows. The GHCR image deployment on Unraid does not need that bind mount.

## User Preferences And Future Context

- The user wants concise, practical steps and prefers working systems over long theory.
- The user is self-hosting on Unraid and currently runs the bot as a normal Unraid Docker container from GHCR.
- The user previously tried Dockge, but moved toward normal Unraid Docker because this is a single-container app.
- The NAS has Ollama with a GPU, Redis, Qdrant, and Adminer available. Do not depend on these by default.
- If AI is added later, use Ollama on demand only; do not keep a model running all the time. Prefer smaller installed models unless a task truly needs a larger one.
- Redis could be useful for short-lived caching/rate-limit protection or command activity counters.
- Qdrant is only relevant if semantic search/memory over discussions or summaries is added.
- SQL or SQLite would be better than Qdrant for straightforward command logs, weekly summaries, watchlists, or user preferences.
- Keep public docs and git history free of personal info, emails, NAS IPs, Discord guild IDs, tokens, and logs.

## Security/Public Repo Notes

The repo was audited for obvious public-safety issues. At the time of this handoff:

- `.env` is ignored by `.gitignore`.
- `.env` and `.git` are excluded from Docker build context by `.dockerignore`.
- Dockerfile copies only `requirements.txt` and `stockbot/`.
- Current reachable commits use a GitHub no-reply email.
- The public README does not include personal email, NAS IP, Discord guild ID, or token.
- Placeholder token examples are okay and intentional.
