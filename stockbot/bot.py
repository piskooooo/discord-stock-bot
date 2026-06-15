from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands

from stockbot.market_data import RANGES, build_chart, clean_symbol, format_money, get_info, get_news


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("stockbot")


class StockBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        guild_id = os.getenv("DISCORD_GUILD_ID")

        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %s commands to guild %s", len(synced), guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %s global commands", len(synced))


bot = StockBot()


async def send_chart(interaction: discord.Interaction, symbol: str, range_key: str) -> None:
    await interaction.response.defer(thinking=True)
    chart_range = RANGES[range_key]
    symbol = clean_symbol(symbol)

    try:
        image, filename, description = await asyncio.to_thread(build_chart, symbol, chart_range)
    except Exception as exc:
        logger.exception("Failed to build chart for %s", symbol)
        await interaction.followup.send(f"Could not get `{symbol}` data: {exc}", ephemeral=True)
        return

    file = discord.File(image, filename=filename)
    embed = discord.Embed(
        title=f"{symbol} - {chart_range.label}",
        description=description,
        color=discord.Color.green() if "Trend: `up`" in description else discord.Color.red(),
    )
    embed.set_image(url=f"attachment://{filename}")
    embed.set_footer(text="Data from Yahoo Finance. For fun, not financial advice.")
    await interaction.followup.send(embed=embed, file=file)


@bot.tree.command(name="mi", description="Show a 1-minute stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def minute(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "mi")


@bot.tree.command(name="da", description="Show a 1-day stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def day(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "da")


@bot.tree.command(name="we", description="Show a 1-week stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def week(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "we")


@bot.tree.command(name="mo", description="Show a 1-month stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def month(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "mo")


@bot.tree.command(name="ytd", description="Show a year-to-date stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def ytd(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "ytd")


@bot.tree.command(name="y1", description="Show a 1-year stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def one_year(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "y1")


@bot.tree.command(name="y5", description="Show a 5-year stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def five_year(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "y5")


@bot.tree.command(name="all", description="Show an all-time stock chart.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def all_time(interaction: discord.Interaction, symbol: str) -> None:
    await send_chart(interaction, symbol, "all")


@bot.tree.command(name="info", description="Show basic stock/company information.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def info(interaction: discord.Interaction, symbol: str) -> None:
    await interaction.response.defer(thinking=True)
    symbol = clean_symbol(symbol)

    try:
        data = await asyncio.to_thread(get_info, symbol)
    except Exception as exc:
        logger.exception("Failed to get info for %s", symbol)
        await interaction.followup.send(f"Could not get `{symbol}` info: {exc}", ephemeral=True)
        return

    description = data.get("summary")
    if not description:
        parts = [part for part in [data.get("quote_type"), data.get("sector"), data.get("industry")] if part]
        description = " / ".join(parts) if parts else "Basic quote information."

    embed = discord.Embed(
        title=f"{data['name']} ({data['symbol']})",
        description=description[:900],
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Exchange", value=data.get("exchange") or "n/a", inline=True)
    embed.add_field(name="Currency", value=data.get("currency") or "n/a", inline=True)
    embed.add_field(name="Market Cap", value=format_money(data.get("market_cap")), inline=True)
    embed.add_field(name="Current Price", value=format_money(data.get("current_price")), inline=True)
    embed.add_field(name="Open", value=format_money(data.get("open")), inline=True)
    embed.add_field(name="Previous Close", value=format_money(data.get("previous_close")), inline=True)
    embed.add_field(
        name="Day Range",
        value=f"{format_money(data.get('day_low'))} - {format_money(data.get('day_high'))}",
        inline=True,
    )
    embed.add_field(
        name="52 Week Range",
        value=(
            f"{format_money(data.get('fifty_two_week_low'))} - "
            f"{format_money(data.get('fifty_two_week_high'))}"
        ),
        inline=True,
    )

    if data.get("sector") or data.get("industry"):
        embed.add_field(
            name="Sector / Industry",
            value=f"{data.get('sector') or 'n/a'} / {data.get('industry') or 'n/a'}",
            inline=False,
        )

    if data.get("website"):
        embed.add_field(name="Website", value=data["website"], inline=False)

    embed.set_footer(text=f"As of {data['as_of']}. Data from Yahoo Finance.")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="news", description="Show recent news for a stock.")
@app_commands.describe(symbol="Ticker symbol, for example AAPL, MSFT, TSLA, SPY, BTC-USD")
async def news(interaction: discord.Interaction, symbol: str) -> None:
    await interaction.response.defer(thinking=True)
    symbol = clean_symbol(symbol)

    try:
        articles = await asyncio.to_thread(get_news, symbol, 5)
    except Exception as exc:
        logger.exception("Failed to get news for %s", symbol)
        await interaction.followup.send(f"Could not get `{symbol}` news: {exc}", ephemeral=True)
        return

    if not articles:
        await interaction.followup.send(f"No recent news found for `{symbol}`.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Recent {symbol} News",
        color=discord.Color.gold(),
    )

    for article in articles:
        title = article["title"][:240]
        link = article["link"]
        value = article["publisher"]

        if article["published"]:
            value += f" | {article['published']}"

        if link:
            value += f"\n{link}"

        embed.add_field(name=title, value=value[:1024], inline=False)

    embed.set_footer(text="News from Yahoo Finance.")
    await interaction.followup.send(embed=embed)


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required.")
    bot.run(token)


if __name__ == "__main__":
    main()
