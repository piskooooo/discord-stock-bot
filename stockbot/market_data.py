from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from io import BytesIO
from itertools import pairwise
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator


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
EXTENDED_MARKET_OPEN = time(8, 0)
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)
EXTENDED_MARKET_CLOSE = time(20, 0)

CHART_COLORS = {
    "background": "#1b1c27",
    "axes": "#1b1c27",
    "grid": "#363744",
    "text": "#e9eaf2",
    "muted": "#999baa",
    "extended_session": "#252638",
    "session_label": "#a0a1bb",
    "up": "#59eeb5",
    "down": "#ff6b7a",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.^=-]{1,30}$")
CRYPTO_QUOTE_SUFFIXES = ("-AUD", "-CAD", "-CHF", "-EUR", "-GBP", "-JPY", "-USD", "-USDT")


def clean_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper().removeprefix("$")

    if not SYMBOL_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Enter a valid ticker symbol, for example `AAPL`, `BRK-B`, or `BTC-USD`."
        )

    return cleaned


def _is_crypto_symbol(symbol: str) -> bool:
    return symbol.endswith(CRYPTO_QUOTE_SUFFIXES)


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
    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    opens = quote.get("open") or []
    lows = quote.get("low") or []
    highs = quote.get("high") or []
    regular_opens: list[float] = []
    regular_lows: list[float] = []
    regular_highs: list[float] = []

    for index, timestamp in enumerate(timestamps):
        local_time = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .astimezone(MARKET_TZ)
            .time()
        )
        if not REGULAR_MARKET_OPEN <= local_time <= REGULAR_MARKET_CLOSE:
            continue

        if index < len(opens) and opens[index] is not None:
            regular_opens.append(opens[index])
        if index < len(lows) and lows[index] is not None:
            regular_lows.append(lows[index])
        if index < len(highs) and highs[index] is not None:
            regular_highs.append(highs[index])

    return {
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "fullExchangeName": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "regularMarketPrice": meta.get("regularMarketPrice"),
        "regularMarketPreviousClose": meta.get("chartPreviousClose")
        or meta.get("previousClose"),
        "regularMarketOpen": regular_opens[0]
        if regular_opens
        else meta.get("regularMarketOpen"),
        "regularMarketDayLow": min(regular_lows)
        if regular_lows
        else meta.get("regularMarketDayLow"),
        "regularMarketDayHigh": max(regular_highs)
        if regular_highs
        else meta.get("regularMarketDayHigh"),
        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
        "marketCap": meta.get("marketCap"),
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


def _change_text(
    history: pd.DataFrame, last_price: float | None = None
) -> tuple[float, float, str]:
    first = float(history["Close"].iloc[0])
    last = float(history["Close"].iloc[-1]) if last_price is None else last_price
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


def _candle_width(date_numbers: list[float], interval: str = "1d") -> float:
    fallback_gap = {
        "1m": 1 / 1440,
        "5m": 5 / 1440,
        "30m": 30 / 1440,
        "1d": 1,
        "1wk": 7,
        "1mo": 30,
    }.get(interval, 1)
    if len(date_numbers) < 2:
        return min(fallback_gap * 0.68, 16)

    gaps = [later - earlier for earlier, later in pairwise(date_numbers) if later > earlier]

    if not gaps:
        return min(fallback_gap * 0.68, 16)

    return min(pd.Series(gaps).median() * 0.68, 16)


def _draw_heikin_ashi_candles(
    ax: plt.Axes, history: pd.DataFrame, interval: str = "1d"
) -> None:
    if history.attrs.get("flat_closed_session"):
        date_numbers = mdates.date2num(history.index.to_pydatetime()).tolist()
        price = float(history["Close"].iloc[-1])
        ax.plot(
            date_numbers,
            [price] * len(date_numbers),
            color=CHART_COLORS["muted"],
            linewidth=1.2,
            alpha=0.95,
        )
        return

    ha = _heikin_ashi(history)
    date_numbers = mdates.date2num(ha.index.to_pydatetime()).tolist()
    width = _candle_width(date_numbers, interval)
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

        ax.vlines(x_value, low, high, color=color, linewidth=0.65, zorder=3)

        if body_height == 0:
            ax.hlines(open_, x_value - width / 2, x_value + width / 2,
                      color=color, linewidth=0.9, zorder=4)
        else:
            ax.add_patch(
                Rectangle(
                    (x_value - width / 2, body_low),
                    width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.4,
                    zorder=4,
                )
            )


def _format_volume(value: float, _position: int) -> str:
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.1f}T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def _draw_volume(ax: plt.Axes, history: pd.DataFrame, interval: str = "1d") -> None:
    label = "VOLUME"
    if "Volume" not in history or history["Volume"].sum() <= 0:
        ax.set_ylim(0, 1)
        ax.set_yticks([])
    else:
        date_numbers = mdates.date2num(history.index.to_pydatetime()).tolist()
        width = _candle_width(date_numbers, interval) * 0.75
        # Measure after the shared time limits and layout are finalized so the
        # rounded strokes stay narrower than their corresponding candles.
        left = ax.transData.transform((date_numbers[0], 0))[0]
        right = ax.transData.transform((date_numbers[0] + width, 0))[0]
        linewidth = max(0.4, (right - left) * 72 / ax.figure.dpi)
        colors = [
            CHART_COLORS["up"] if close >= open_ else CHART_COLORS["down"]
            for open_, close in zip(history["Open"], history["Close"])
        ]
        # Retain raw heights; only the axes clip an isolated extreme spike.
        positive = history["Volume"] > 0
        ax.vlines(
            [value for value, keep in zip(date_numbers, positive) if keep],
            0, history.loc[positive, "Volume"],
            colors=[color for color, keep in zip(colors, positive) if keep],
            linewidth=linewidth, capstyle="round", zorder=3,
        )
        ax.yaxis.set_major_formatter(FuncFormatter(_format_volume))

        ceiling = ax.get_ylim()[1]
        for x_value, volume in zip(date_numbers, history["Volume"]):
            if not volume > ceiling:
                continue
            label = "VOLUME · spike clipped"
            ax.text(
                x_value, 0.78, "//", transform=ax.get_xaxis_transform(),
                ha="center", va="center", color=CHART_COLORS["text"],
                fontsize=9, fontweight="bold", zorder=4,
                bbox={"facecolor": CHART_COLORS["axes"], "edgecolor": "none", "pad": 0.3},
            )
            x_position = (x_value - ax.get_xlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])
            near_right = x_position > 0.85
            ax.annotate(
                _format_volume(float(volume), 0),
                (x_value, 0.60 if x_position < 0.2 else 0.97),
                xycoords=ax.get_xaxis_transform(), xytext=(-7 if near_right else 7, 0),
                textcoords="offset points", ha="right" if near_right else "left",
                va="top", fontsize=8, color=CHART_COLORS["text"], zorder=4,
            )

    ax.text(0.008, 0.94, label, transform=ax.transAxes,
            color=CHART_COLORS["muted"], fontsize=7, va="top", zorder=4)


def _single_day_history(
    history: pd.DataFrame,
    market_date: date | None = None,
) -> pd.DataFrame:
    market_date = market_date or datetime.now(MARKET_TZ).date()
    local_datetimes = [index.astimezone(MARKET_TZ) for index in history.index]
    mask = [
        local_datetime.date() == market_date
        and EXTENDED_MARKET_OPEN <= local_datetime.time() <= EXTENDED_MARKET_CLOSE
        for local_datetime in local_datetimes
    ]
    session_history = history.loc[mask]
    return (
        session_history
        if not session_history.empty
        else _flat_closed_session_history(history, market_date)
    )


def _latest_regular_session_history(history: pd.DataFrame) -> pd.DataFrame:
    local_datetimes = [index.astimezone(MARKET_TZ) for index in history.index]
    regular_mask = [
        REGULAR_MARKET_OPEN <= local_datetime.time() <= REGULAR_MARKET_CLOSE
        for local_datetime in local_datetimes
    ]
    regular_history = history.loc[regular_mask]
    if regular_history.empty:
        return history

    latest_date = regular_history.index[-1].astimezone(MARKET_TZ).date()
    latest_mask = [
        index.astimezone(MARKET_TZ).date() == latest_date
        for index in regular_history.index
    ]
    return regular_history.loc[latest_mask]


def _flat_closed_session_history(
    history: pd.DataFrame,
    market_date: date | None = None,
) -> pd.DataFrame:
    market_date = market_date or datetime.now(MARKET_TZ).date()
    market_open = datetime.combine(market_date, REGULAR_MARKET_OPEN, MARKET_TZ)
    market_close = datetime.combine(market_date, REGULAR_MARKET_CLOSE, MARKET_TZ)
    price = float(history["Close"].iloc[-1])
    index = pd.date_range(market_open, market_close, freq="5min")
    flat_history = pd.DataFrame(
        {
            "Open": price,
            "High": price,
            "Low": price,
            "Close": price,
            "Volume": 0,
        },
        index=index,
    )
    flat_history.index.name = history.index.name
    flat_history.attrs["flat_closed_session"] = True
    return flat_history


def _set_price_ylim(ax: plt.Axes, history: pd.DataFrame) -> None:
    low = float(history["Low"].min())
    high = float(history["High"].max())
    price_range = high - low

    if price_range <= 0:
        padding = max(high * 0.001, 0.01)
    else:
        padding = price_range * 0.08

    # Heikin-Ashi opens can extend beyond an individual raw candle's range.
    ha = _heikin_ashi(history)
    ax.set_ylim(min(low, float(ha["Low"].min())) - padding,
                max(high, float(ha["High"].max())) + padding)


def _set_volume_ylim(ax: plt.Axes, history: pd.DataFrame) -> None:
    if "Volume" not in history:
        return
    positive = history.loc[history["Volume"] > 0, "Volume"]
    if positive.empty:
        return
    peak = float(positive.max())
    ceiling = peak * 1.18
    # Only trim a single extreme outlier with enough surrounding observations.
    # Sparse samples and broad volume surges keep their full linear scale.
    if len(positive) >= 20:
        second_largest = float(positive.nlargest(2).iloc[1])
        if peak >= second_largest * 5:
            ceiling = second_largest * 1.25
    ax.set_ylim(0, ceiling)


def _set_intraday_session_xlim(ax: plt.Axes, history: pd.DataFrame) -> None:
    market_date = history.index[-1].astimezone(MARKET_TZ).date()
    market_open = datetime.combine(market_date, EXTENDED_MARKET_OPEN, MARKET_TZ)
    market_close = datetime.combine(market_date, EXTENDED_MARKET_CLOSE, MARKET_TZ)
    ax.set_xlim(mdates.date2num(market_open), mdates.date2num(market_close))


def _set_intraday_session_ticks(ax: plt.Axes, history: pd.DataFrame) -> None:
    market_date = history.index[-1].astimezone(MARKET_TZ).date()
    ticks = [
        datetime.combine(market_date, time(hour, 0), MARKET_TZ)
        for hour in range(EXTENDED_MARKET_OPEN.hour, EXTENDED_MARKET_CLOSE.hour + 1)
    ]
    ax.xaxis.set_major_locator(FixedLocator(mdates.date2num(ticks)))
    ax.xaxis.set_major_formatter(FuncFormatter(_format_intraday_tick))


def _shade_extended_sessions(
    ax: plt.Axes, volume_ax: plt.Axes, history: pd.DataFrame
) -> None:
    market_date = history.index[-1].astimezone(MARKET_TZ).date()
    sessions = (
        (EXTENDED_MARKET_OPEN, REGULAR_MARKET_OPEN, "PRE-MARKET"),
        (REGULAR_MARKET_CLOSE, EXTENDED_MARKET_CLOSE, "AFTER-HOURS"),
    )
    for start, end, label in sessions:
        left, right = mdates.date2num([
            datetime.combine(market_date, start, MARKET_TZ),
            datetime.combine(market_date, end, MARKET_TZ),
        ])
        for chart_ax in (ax, volume_ax):
            chart_ax.axvspan(
                left, right, facecolor=CHART_COLORS["extended_session"],
                edgecolor="none", zorder=0,
            )
        ax.text(
            (left + right) / 2, 0.98, label, transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=8, fontweight="bold",
            color=CHART_COLORS["session_label"], zorder=4,
        )


def _format_intraday_tick(value: float, _position: int) -> str:
    tick_time = mdates.num2date(value, tz=MARKET_TZ)
    return tick_time.strftime("%H:%M")


def _format_price(value: float, _position: int = 0, precision: int = 2) -> str:
    return f"{value:,.{precision}f}"


def _price_precision(low: float, high: float, price: float) -> int:
    precision = max(2, -math.floor(math.log10((high - low) / 7))) if high > low else 2
    if 0 < abs(price) < 1:
        precision = max(precision, 3 - math.floor(math.log10(abs(price))))
    return precision


def _draw_chart_header(
    fig: plt.Figure, symbol: str, chart_range: ChartRange,
    history: pd.DataFrame, change: float, percent: float,
) -> float:
    last = float(history["Close"].iloc[-1])
    low, high = float(history["Low"].min()), float(history["High"].max())
    precision = _price_precision(low, high, last)
    is_closed = bool(history.attrs.get("flat_closed_session"))
    if is_closed:
        details = f"Last: {_format_price(last, precision=precision)}"
    else:
        volume = (
            _format_volume(float(history["Volume"].sum()), 0)
            if "Volume" in history and history["Volume"].notna().any() else "—"
        )
        details = (
            f"O: {_format_price(float(history['Open'].iloc[0]), precision=precision)}  "
            f"H: {_format_price(high, precision=precision)}  "
            f"L: {_format_price(low, precision=precision)}  "
            f"C: {_format_price(last, precision=precision)}  Vol: {volume}"
        )
    left = fig.text(
        0.035, 0.965, f"{symbol} · {details}", ha="left", va="top",
        color=CHART_COLORS["text"], fontsize=12, fontweight="bold",
    )
    right = fig.text(
        0.965, 0.965, f"{change:+,.{precision}f} ({percent:+.2f}%)",
        ha="right", va="top", fontsize=12, fontweight="bold",
        color=CHART_COLORS["up" if change > 0 else "down" if change < 0 else "muted"],
    )
    renderer = fig.canvas.get_renderer()
    gap = 20 * fig.dpi / 150
    right_edge = right.get_window_extent(renderer).x0 - gap

    def fit_left(edge: float) -> None:
        while left.get_window_extent(renderer).x1 > edge and left.get_fontsize() > 9:
            left.set_fontsize(left.get_fontsize() - 0.5)

    fit_left(right_edge)
    if left.get_window_extent(renderer).x1 > right_edge:
        # Unusually long tickers or precise prices can use a second row.
        left.set_text(f"{symbol}\n{details}")
        left.set_fontsize(12)
        fit_left(fig.bbox.width * 0.965)

    header_bottom = min(left.get_window_extent(renderer).y0, right.get_window_extent(renderer).y0)
    context_y = header_bottom / fig.bbox.height - 0.012
    start = history.index[0].astimezone(MARKET_TZ)
    end = history.index[-1].astimezone(MARKET_TZ)
    dates = end.strftime("%b %d, %Y") if start.date() == end.date() else (
        f"{start:%b %d, %Y} – {end:%b %d, %Y}"
    )
    context = f"{chart_range.label} · Heikin-Ashi · {dates} ET"
    if is_closed:
        context += " · Market closed · carry-forward price"
    context_text = fig.text(
        0.035, context_y, context, ha="left", va="top",
        fontsize=8, color=CHART_COLORS["muted"],
    )
    fig.text(
        0.965, context_y, "vs prior session start" if is_closed else "vs first displayed close",
        ha="right", va="top", fontsize=8, color=CHART_COLORS["muted"],
    )
    return context_text.get_window_extent(renderer).y0 / fig.bbox.height - 0.025


def _draw_last_price(ax: plt.Axes, price: float, color: str) -> None:
    low, high = ax.get_ylim()
    precision = _price_precision(low, high, price)
    ax.axhline(price, color=color, linewidth=0.75, linestyle=(0, (2, 3)),
               alpha=0.7, zorder=2)
    ax.text(
        1.012, price, _format_price(price, precision=precision),
        transform=ax.get_yaxis_transform(),
        ha="left", va="center", color=CHART_COLORS["background"],
        fontsize=10, fontweight="bold", clip_on=False, zorder=5,
        bbox={"boxstyle": "round,pad=0.3,rounding_size=0.12",
              "facecolor": color, "edgecolor": "none"},
    )
    # Leave a gap in the tick labels wherever the price badge sits.
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda value, position: "" if abs(value - price) < (high - low) * 0.05
        else _format_price(value, position, precision)
    ))


def build_chart(symbol: str, chart_range: ChartRange) -> tuple[BytesIO, str, str]:
    symbol = clean_symbol(symbol)
    history = get_history(symbol, chart_range)
    use_stock_session = (
        chart_range.period == "1d"
        and chart_range.interval in {"1m", "5m", "30m"}
        and not _is_crypto_symbol(symbol)
    )
    display_history = history
    if use_stock_session:
        market_date = (
            datetime.now(MARKET_TZ).date() if chart_range.show_full_trading_day
            else history.index[-1].astimezone(MARKET_TZ).date()
        )
        display_history = _single_day_history(history, market_date)
    last_price = float(display_history["Close"].iloc[-1])
    change_history = (
        _latest_regular_session_history(history)
        if display_history.attrs.get("flat_closed_session")
        else display_history
    )
    change, percent, arrow = _change_text(change_history, last_price)
    summary = (
        f"Last: ${last_price:,.2f} | Change: {change:+.2f} "
        f"({percent:+.2f}%) | Trend: {arrow}"
    )
    if display_history.attrs.get("flat_closed_session"):
        summary += " | Market closed"

    fig, (ax, volume_ax) = plt.subplots(
        2,
        1,
        figsize=(11.2, 6.4),
        dpi=150,
        sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1], "hspace": 0.045},
    )
    fig.patch.set_facecolor(CHART_COLORS["background"])
    for chart_ax in (ax, volume_ax):
        chart_ax.set_facecolor(CHART_COLORS["axes"])

    ax.text(
        0.5, 0.5, symbol, transform=ax.transAxes, ha="center", va="center",
        fontsize=min(110, 500 / len(symbol)), fontweight="bold",
        color=CHART_COLORS["text"], alpha=0.035, zorder=1,
    )
    _draw_heikin_ashi_candles(ax, display_history, chart_range.interval)
    volume_ax.yaxis.set_major_locator(MaxNLocator(nbins=3, min_n_ticks=2))
    _set_price_ylim(ax, display_history)
    _set_volume_ylim(volume_ax, display_history)

    plot_top = _draw_chart_header(fig, symbol, chart_range, display_history, change, percent)
    volume_ax.set_xlabel("")
    ax.margins(x=0.025)

    for chart_ax in (ax, volume_ax):
        chart_ax.yaxis.tick_right()
        chart_ax.yaxis.set_label_position("right")
        chart_ax.tick_params(axis="both", colors=CHART_COLORS["muted"],
                             labelsize=9, length=0, pad=9)
        chart_ax.set_axisbelow(True)
        chart_ax.grid(True, color=CHART_COLORS["grid"], alpha=0.65, linewidth=0.5)

        for spine in chart_ax.spines.values():
            spine.set_visible(False)

    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, min_n_ticks=4))
    price_color = CHART_COLORS[
        "muted" if display_history.attrs.get("flat_closed_session") else arrow
    ]
    _draw_last_price(ax, last_price, price_color)

    date_locator = mdates.AutoDateLocator(tz=MARKET_TZ, minticks=4, maxticks=8)
    volume_ax.xaxis.set_major_locator(date_locator)
    volume_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(date_locator, tz=MARKET_TZ))
    volume_ax.xaxis.get_offset_text().set_color(CHART_COLORS["muted"])

    if use_stock_session:
        _shade_extended_sessions(ax, volume_ax, display_history)
        _set_intraday_session_xlim(ax, display_history)
        _set_intraday_session_ticks(volume_ax, display_history)

    fig.subplots_adjust(left=0.035, right=0.90, bottom=0.09, top=plot_top)
    volume_ax.set_xlim(ax.get_xlim())
    _draw_volume(volume_ax, display_history, chart_range.interval)
    fig.text(
        0.035, 0.02, "Data from Yahoo Finance.", ha="left", va="center",
        fontsize=7, color=CHART_COLORS["muted"],
    )

    image = BytesIO()
    fig.savefig(
        image,
        format="png",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    image.seek(0)

    filename = f"{symbol.lower()}-{chart_range.period}-{chart_range.interval}.png"
    return image, filename, summary


def get_info(symbol: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol)
    try:
        quote = _get_quote(symbol)
    except Exception:  # noqa: BLE001 - each source is an optional best-effort fallback.
        quote = {}

    try:
        search_profile = _get_search_profile(symbol)
    except Exception:  # noqa: BLE001 - each source is an optional best-effort fallback.
        search_profile = {}

    ticker = yf.Ticker(symbol)
    try:
        info = ticker.get_info()
    except Exception:  # noqa: BLE001 - yfinance can raise several backend exception types.
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

    if not math.isfinite(value):
        return "n/a"

    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"
