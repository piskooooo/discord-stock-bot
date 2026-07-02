# Privacy Policy

Last updated: 2026-07-02

Discord Stock Bot is a small self-hosted Discord bot for stock charts, basic ticker information, and recent market news.

## Data The Bot Uses

The bot receives the Discord slash-command interaction data needed to respond to a command, including the command name, ticker symbol entered by the user, server/channel context supplied by Discord, and the requesting Discord user information included with the interaction.

The bot does not request Discord message content intent, does not read general chat messages, does not ask for Discord passwords or tokens, and does not sell or share Discord user data.

## Data Storage

The bot does not intentionally store Discord user data, command history, ticker requests, chart images, or Yahoo Finance response data in an application database.

Operational logs may contain basic runtime events and error details. Do not configure logs to include Discord tokens, private server IDs, screenshots, or other secrets.

Runtime secrets such as `DISCORD_TOKEN` and optional `DISCORD_GUILD_ID` must be supplied through environment variables on the host and must not be committed to the repository or baked into Docker images.

## Third-Party Services

The bot contacts Discord APIs to receive and respond to slash commands.

The bot contacts Yahoo Finance endpoints to fetch ticker chart data, quote/profile information, and recent news links. Yahoo Finance may receive the ticker symbol requested by a user and the request metadata normally sent with an HTTP request.

## Financial Disclaimer

The bot is for personal convenience and entertainment. It does not provide financial, investment, tax, or legal advice. Market data and news can be delayed, incomplete, unavailable, or inaccurate.

## Contact And Reports

For private deployments, users should contact the server owner or bot operator to report issues, request removal, or ask privacy questions.
