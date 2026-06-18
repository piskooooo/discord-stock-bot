from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from io import BytesIO
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
import pandas as pd
import requests
import yfinance as yf


@dataclass(frozen=True)
class ChartRange:
    label: str
    period: str
    interval: str
    show_full_trading_day: bool = False


RANGES: dict[str, ChartRange] = {
    "mi": ChartRange("5 minute", "1d", "5m", True),
    "da": ChartRange("1 day", "1d", "5m"),
    "we": ChartRange("1 week", "5d", "30m"),
    "mo": ChartRange("1 month", "1mo", "1d"),
    "ytd": ChartRange("YTD", "ytd", "1d"),
    "y1": ChartRange("1 year", "1y", "1d"),
    "y5": ChartRange("5 years", "5y", "1wk"),
    "all": ChartRange("all time", "max", "1mo"),
}

MARKET_TZ = ZoneInfo("America/New_York")
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)

CHART_COLORS = {
    "background": "#0d1117",
    "axes": "#111827",
    "grid": "#30363d",
    "text": "#e6edf3",
    "muted": "#9ca3af",
    "up": "#22c55e",
    "down": "#ef4444",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


def clean_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("$", "")


def get_history(symbol: str, chart_range: ChartRange) -> pd.DataFrame:
    symbol = clean_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = requests.get(
        url,
        params={
            "range": chart_range.period,
            "interval": chart_range.interval,
            "includePrePost": "true",
        },
        headers=HEADERS,
        timeout=15,
    )

    if response.status_code == 429:
        raise ValueError("Yahoo Finance is rate limiting requests. Wait a bit and try again.")

    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]

    if not result:
        error = payload.get("chart", {}).get("error") or {}
        description = error.get("description") or f"No market data found for `{symbol}`."
        raise ValueError(description)

    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    if len(volumes) < len(timestamps):
        volumes = volumes + [0] * (len(timestamps) - len(volumes))

    rows = [
        (datetime.fromtimestamp(ts, tz=timezone.utc), open_, high, low, close, volume or 0)
        for ts, open_, high, low, close, volume in zip(timestamps, opens, highs, lows, closes, volumes)
        if None not in (open_, high, low, close)
    ]

    history = pd.DataFrame(
        rows,
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    ).set_index("Date")

    if history.empty:
        raise ValueError(f"No market data found for `{symbol}`.")

    return history


def _get_quote(symbol: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol)
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": "1d", "interval": "5m", "includePrePost": "true"},
        headers=HEADERS,
        timeout=15,
    )

    if response.status_code == 429:
        raise ValueError("Yahoo Finance is rate limiting requests. Wait a bit and try again.")

    response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [None])[0]

    if not result:
        return {}

    meta = result.get("meta") or {}
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    opens = [value for value in quote.get("open", []) if value is not None]
    lows = [value for value in quote.get("low", []) if value is not None]
    highs = [value for value in quote.get("high", []) if value is not None]

    return {
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "fullExchangeName": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "regularMarketPrice": meta.get("regularMarketPrice"),
        "regularMarketPreviousClose": meta.get("chartPreviousClose") or meta.get("previousClose"),
        "regularMarketOpen": opens[0] if opens else None,
        "regularMarketDayLow": min(lows) if lows else None,
        "regularMarketDayHigh": max(highs) if highs else None,
        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
    }


def _get_search_profile(symbol: str) -> dict[str, Any]:
    response = requests.get(
        "https://query1.finance.yahoo.com/v1/finance/search",
        params={"q": clean_symbol(symbol), "quotesCount": 1, "newsCount": 0},
        headers=HEADERS,
        timeout=15,
    )

    if response.status_code == 429:
        return {}

    response.raise_for_status()
    quotes = response.json().get("quotes") or []
    return quotes[0] if quotes else {}


def _change_text(history: pd.DataFrame) -> tuple[float, float, str]:
    first = float(history["Close"].iloc[0])
    last = float(history["Close"].iloc[-1])
    change = last - first
    percent = (change / first) * 100 if first else 0
    arrow = "up" if change >= 0 else "down"
    return change, percent, arrow


def _heikin_ashi(history: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=history.index)
    ha["Close"] = (history["Open"] + history["High"] + history["Low"] + history["Close"]) / 4

    opens = []
    for index, row in enumerate(history.itertuples()):
        if index == 0:
            opens.append((row.Open + row.Close) / 2)
        else:
            opens.append((opens[index - 1] + ha["Close"].iloc[index - 1]) / 2)

    ha["Open"] = opens
    ha["High"] = pd.concat([history["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([history["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
    return ha[["Open", "High", "Low", "Close"]]


def _candle_width(date_numbers: list[float]) -> float:
    if len(date_numbers) < 2:
        return 0.6

    gaps = [
        later - earlier
        for earlier, later in zip(date_numbers, date_numbers[1:])
        if later > earlier
    ]

    if not gaps:
        return 0.6

    return min(pd.Series(gaps).median() * 0.72, 16)


def _draw_heikin_ashi_candles(ax: plt.Axes, history: pd.DataFrame) -> None:
    ha = _heikin_ashi(history)
    date_numbers = mdates.date2num(ha.index.to_pydatetime()).tolist()
    width = _candle_width(date_numbers)
    up_color = CHART_COLORS["up"]
    down_color = CHART_COLORS["down"]

    for x_value, candle in zip(date_numbers, ha.itertuples()):
        open_ = float(candle.Open)
        high = float(candle.High)
        low = float(candle.Low)
        close = float(candle.Close)
        color = up_color if close >= open_ else down_color
        body_low = min(open_, close)
        body_height = abs(close - open_)

        ax.vlines(x_value, low, high, color=color, linewidth=1.1, alpha=0.95)

        if body_height == 0:
            ax.hlines(open_, x_value - width / 2, x_value + width / 2, color=color, linewidth=1.6)
        else:
            ax.add_patch(
                Rectangle(
                    (x_value - width / 2, body_low),
                    width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.8,
                    alpha=0.88,
                )
            )


def _format_volume(value: float, _position: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def _draw_volume(ax: plt.Axes, history: pd.DataFrame) -> None:
    if "Volume" not in history or history["Volume"].sum() <= 0:
        ax.set_visible(False)
        return

    date_numbers = mdates.date2num(history.index.to_pydatetime()).tolist()
    width = _candle_width(date_numbers)
    colors = [
        CHART_COLORS["up"] if close >= open_ else CHART_COLORS["down"]
        for open_, close in zip(history["Open"], history["Close"])
    ]

    ax.bar(
        date_numbers,
        history["Volume"],
        width=width,
        color=colors,
        alpha=0.45,
        align="center",
    )
    ax.set_ylabel("Volume")
    ax.yaxis.set_major_formatter(FuncFormatter(_format_volume))


def _set_regular_session_xlim(ax: plt.Axes, history: pd.DataFrame) -> None:
    market_date = history.index[-1].astimezone(MARKET_TZ).date()
    market_open = datetime.combine(market_date, REGULAR_MARKET_OPEN, MARKET_TZ)
    market_close = datetime.combine(market_date, REGULAR_MARKET_CLOSE, MARKET_TZ)
    ax.set_xlim(mdates.date2num(market_open), mdates.date2num(market_close))


def build_chart(symbol: str, chart_range: ChartRange) -> tuple[BytesIO, str, str]:
    history = get_history(symbol, chart_range)
    symbol = clean_symbol(symbol)
    change, percent, arrow = _change_text(history)
    last_price = float(history["Close"].iloc[-1])

    fig, (ax, volume_ax) = plt.subplots(
        2,
        1,
        figsize=(10, 6.2),
        dpi=150,
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
    )
    fig.patch.set_facecolor(CHART_COLORS["background"])
    for chart_ax in (ax, volume_ax):
        chart_ax.set_facecolor(CHART_COLORS["axes"])

    _draw_heikin_ashi_candles(ax, history)
    _draw_volume(volume_ax, history)

    ax.set_title(
        f"{symbol} - {chart_range.label} Heikin-Ashi",
        color=CHART_COLORS["text"],
        fontsize=15,
        fontweight="bold",
    )
    ax.set_ylabel("Price")
    volume_ax.set_xlabel("")
    ax.margins(x=0.01)
    volume_ax.margins(x=0.01)

    for chart_ax in (ax, volume_ax):
        chart_ax.yaxis.label.set_color(CHART_COLORS["muted"])
        chart_ax.tick_params(axis="both", colors=CHART_COLORS["muted"])
        chart_ax.grid(True, color=CHART_COLORS["grid"], alpha=0.55, linewidth=0.8)

        for spine in chart_ax.spines.values():
            spine.set_color(CHART_COLORS["grid"])

    if chart_range.interval in {"1m", "5m", "30m"}:
        volume_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M", tz=MARKET_TZ))
    else:
        volume_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

    if chart_range.show_full_trading_day:
        _set_regular_session_xlim(ax, history)

    fig.autofmt_xdate()
    fig.tight_layout()

    image = BytesIO()
    fig.savefig(
        image,
        format="png",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    image.seek(0)

    description = (
        f"Last: `${last_price:,.2f}` | Change: `{change:+.2f}` "
        f"(`{percent:+.2f}%`) | Trend: `{arrow}`"
    )
    filename = f"{symbol.lower()}-{chart_range.period}-{chart_range.interval}.png"
    return image, filename, description


def get_info(symbol: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol)
    try:
        quote = _get_quote(symbol)
    except Exception:
        quote = {}

    try:
        search_profile = _get_search_profile(symbol)
    except Exception:
        search_profile = {}

    ticker = yf.Ticker(symbol)
    try:
        info = ticker.get_info()
    except Exception:
        info = {}

    return {
        "symbol": symbol,
        "name": (
            info.get("longName")
            or search_profile.get("longname")
            or search_profile.get("shortname")
            or symbol
        ),
        "exchange": (
            info.get("exchange")
            or quote.get("fullExchangeName")
            or search_profile.get("exchDisp")
            or quote.get("exchange")
        ),
        "currency": info.get("currency") or quote.get("currency"),
        "quote_type": search_profile.get("typeDisp") or info.get("quoteType"),
        "sector": info.get("sector") or search_profile.get("sector"),
        "industry": info.get("industry") or search_profile.get("industry"),
        "market_cap": info.get("marketCap") or quote.get("marketCap"),
        "current_price": info.get("currentPrice") or quote.get("regularMarketPrice"),
        "previous_close": info.get("previousClose") or quote.get("regularMarketPreviousClose"),
        "open": info.get("open") or quote.get("regularMarketOpen"),
        "day_low": info.get("dayLow") or quote.get("regularMarketDayLow"),
        "day_high": info.get("dayHigh") or quote.get("regularMarketDayHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow") or quote.get("fiftyTwoWeekLow"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh") or quote.get("fiftyTwoWeekHigh"),
        "website": info.get("website"),
        "summary": info.get("longBusinessSummary"),
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_news(symbol: str, limit: int = 5) -> list[dict[str, str]]:
    symbol = clean_symbol(symbol)
    response = requests.get(
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
        params={"s": symbol, "region": "US", "lang": "en-US"},
        headers=HEADERS,
        timeout=15,
    )

    if response.status_code == 429:
        raise ValueError("Yahoo Finance is rate limiting requests. Wait a bit and try again.")

    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    items: list[dict[str, str]] = []

    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title") or "Untitled"
        link = item.findtext("link") or ""
        publisher = item.findtext("source") or "Yahoo Finance"
        published_text = item.findtext("pubDate") or ""

        items.append(
            {
                "title": title,
                "link": link,
                "publisher": publisher,
                "published": published_text,
            }
        )

    return items


def format_money(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"
