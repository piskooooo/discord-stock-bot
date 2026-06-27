# Agent Guidance

## Project Goal

This is a small Discord stock bot for a private friend-group server. It provides slash commands for stock charts, recent news, and basic ticker info. The current deployment path is a public GitHub repo that builds a public GHCR Docker image for Unraid Docker.

## Current Deployment

- Public repo: `piskooooo/discord-stock-bot`
- Public image: `ghcr.io/piskooooo/discord-stock-bot:latest`
- Runtime secrets live only in Unraid environment variables. Never commit `.env`, tokens, guild IDs, NAS IPs, logs, or screenshots containing them.
- After code changes, commit and push to `main`, then verify the GitHub Actions Docker image workflow succeeds before telling the user to update Unraid.

## Commands

```bash
python3 -m py_compile stockbot/bot.py stockbot/market_data.py
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m stockbot.bot
docker compose up -d --build
gh run list --repo piskooooo/discord-stock-bot --limit 3
```

## Conventions

- Keep the bot simple, self-hostable, and lightweight.
- Prefer small, focused changes over broad refactors.
- Preserve dark-mode Heikin-Ashi chart styling unless the user asks otherwise.
- Do not add AI/Ollama, Redis, Qdrant, or SQL dependencies unless a feature clearly needs them.
- If AI is added later, make it on-demand only; do not keep a model running 24/7. Prefer smaller Ollama models unless quality requires otherwise.
- Treat Yahoo Finance endpoints as unofficial and fragile. Keep error messages friendly and avoid exposing tracebacks to Discord users.
- Keep public docs free of personal info. Use placeholders for tokens and IDs.

## More Context

See `docs/handoff.md` for product status, architecture, open tasks, and fragile areas.
