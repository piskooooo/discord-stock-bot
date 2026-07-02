# Compliance Notes

Last reviewed: 2026-07-02

This project is a private friend-group Discord bot, not a commercial financial product. These notes are an engineering checklist, not legal advice.

## Discord

- Keep the bot's Developer Portal description accurate: stock charts, basic ticker info, and recent news.
- Link `PRIVACY.md` and `TERMS.md` from the bot/application profile if the bot is distributed beyond a single private server.
- Use only required permissions: `bot`, `applications.commands`, `Send Messages`, `Embed Links`, and `Attach Files`.
- Keep default intents only. Do not enable privileged message-content, member, or presence intents unless a future feature truly needs them.
- Do not DM users, advertise to users, profile users, sell user data, or use Discord API data for unrelated purposes.
- Provide a way for server users to report issues to the bot operator.

## Secrets And Public Repo Safety

- Never commit `.env`, Discord tokens, guild IDs, NAS IPs, logs, or screenshots containing private details.
- Keep `.env` in `.gitignore` and `.dockerignore`.
- Keep runtime secrets in Unraid environment variables or another host secret mechanism.
- Do not bake secrets into Docker images.

## Yahoo Finance And Market Data

- Yahoo Finance endpoints are unofficial/fragile for this use case. Avoid presenting the bot as a guaranteed real-time or licensed market data feed.
- Keep data-source attribution visible in Discord embeds and docs.
- Keep usage low-volume and personal/private. Do not monetize Yahoo-derived data or build paid features around it without reviewing and satisfying Yahoo's current terms.
- Do not persist Yahoo response data unless a future design explicitly reviews upstream retention and licensing requirements.
- Keep rate-limit errors friendly and avoid exposing raw upstream exceptions to Discord users.

## News

- `/news` uses Yahoo Finance RSS links, not NewsAPI.org.
- Do not copy full article text into Discord. Link to the original article and preserve publisher/source labels.
- If a future feature switches to NewsAPI.org or another news provider, review that provider's production-use, attribution, caching, and plan requirements before deploying.

## Financial Disclaimer

- Keep "not financial advice" language in chart embeds, docs, and terms.
- Do not add trading automation, alerts that imply guarantees, recommendations, or personalized investment advice without a dedicated legal/product review.

## Deployment

- Public GHCR image is acceptable only if it contains code and dependencies, not secrets.
- After code changes, run `python3 -m py_compile stockbot/bot.py stockbot/market_data.py`, commit, push to `main`, and verify the GitHub Actions Docker image workflow succeeds.
