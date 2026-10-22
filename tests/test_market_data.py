from __future__ import annotations

import math
from datetime import date, datetime
from unittest import TestCase, mock

import pandas as pd

from stockbot import market_data


def _history(rows: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    )
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True)
    return frame.set_index("Date")


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.payload


class MarketDataTests(TestCase):
    def test_clean_symbol_accepts_common_yahoo_formats(self) -> None:
        self.assertEqual(market_data.clean_symbol(" $brk-b "), "BRK-B")
        self.assertEqual(market_data.clean_symbol("btc-usd"), "BTC-USD")
        self.assertEqual(market_data.clean_symbol("^gspc"), "^GSPC")
        self.assertEqual(market_data.clean_symbol("cl=f"), "CL=F")

    def test_clean_symbol_rejects_empty_or_path_like_input(self) -> None:
        for symbol in ("", "$$AAPL", "../AAPL", "AAPL/quote", "AAPL ticker"):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                market_data.clean_symbol(symbol)

    def test_crypto_symbols_do_not_use_stock_market_hours(self) -> None:
        self.assertTrue(market_data._is_crypto_symbol("BTC-USD"))
        self.assertTrue(market_data._is_crypto_symbol("ETH-EUR"))
        self.assertFalse(market_data._is_crypto_symbol("AAPL"))
        self.assertFalse(market_data._is_crypto_symbol("BRK-B"))

    def test_heikin_ashi_calculation(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 10, 13, 9, 12, 100),
                ("2026-08-07 14:05", 12, 15, 11, 14, 120),
            ]
        )

        result = market_data._heikin_ashi(history)

        self.assertEqual(result["Open"].tolist(), [11.0, 11.0])
        self.assertEqual(result["Close"].tolist(), [11.0, 13.0])
        self.assertEqual(result["High"].tolist(), [13.0, 15.0])
        self.assertEqual(result["Low"].tolist(), [9.0, 11.0])

    def test_regular_session_uses_only_requested_market_date(self) -> None:
        history = _history(
            [
                ("2026-08-06 14:00", 90, 92, 89, 91, 100),
                ("2026-08-07 12:00", 98, 99, 97, 98, 20),
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 21:00", 103, 104, 102, 103, 30),
            ]
        )

        result = market_data._regular_session_history(history, date(2026, 8, 7))

        self.assertFalse(result.attrs.get("flat_closed_session", False))
        self.assertEqual(result["Close"].tolist(), [101])

    def test_closed_day_creates_flat_line_for_requested_date(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 21:00", 103, 104, 102, 103, 30),
            ]
        )

        result = market_data._regular_session_history(history, date(2026, 8, 8))

        self.assertTrue(result.attrs["flat_closed_session"])
        self.assertEqual(len(result), 79)
        self.assertEqual(result.index[0].date(), date(2026, 8, 8))
        self.assertTrue((result["Close"] == 103).all())
        self.assertEqual(result["Volume"].sum(), 0)

    def test_quote_day_values_exclude_pre_and_post_market(self) -> None:
        eastern = market_data.MARKET_TZ
        times = [
            datetime(2026, 8, 7, 8, 0, tzinfo=eastern),
            datetime(2026, 8, 7, 9, 30, tzinfo=eastern),
            datetime(2026, 8, 7, 16, 0, tzinfo=eastern),
            datetime(2026, 8, 7, 17, 0, tzinfo=eastern),
        ]
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [int(value.timestamp()) for value in times],
                        "meta": {"regularMarketPrice": 110, "currency": "USD"},
                        "indicators": {
                            "quote": [
                                {
                                    "open": [95, 100, 109, 112],
                                    "low": [90, 99, 108, 107],
                                    "high": [98, 105, 111, 115],
                                }
                            ]
                        },
                    }
                ]
            }
        }

        with mock.patch.object(
            market_data.requests, "get", return_value=FakeResponse(payload)
        ):
            quote = market_data._get_quote("AAPL")

        self.assertEqual(quote["regularMarketOpen"], 100)
        self.assertEqual(quote["regularMarketDayLow"], 99)
        self.assertEqual(quote["regularMarketDayHigh"], 111)

    def test_info_falls_back_when_richer_profile_fails(self) -> None:
        ticker = mock.Mock()
        ticker.get_info.side_effect = RuntimeError("unavailable")

        with (
            mock.patch.object(
                market_data,
                "_get_quote",
                return_value={"regularMarketPrice": 123.45, "currency": "USD"},
            ),
            mock.patch.object(
                market_data,
                "_get_search_profile",
                return_value={"shortname": "Example Corp", "typeDisp": "Equity"},
            ),
            mock.patch.object(market_data.yf, "Ticker", return_value=ticker),
        ):
            info = market_data.get_info("EXM")

        self.assertEqual(info["name"], "Example Corp")
        self.assertEqual(info["current_price"], 123.45)
        self.assertEqual(info["currency"], "USD")
        self.assertEqual(info["quote_type"], "Equity")

    def test_build_chart_returns_a_png_with_summary(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 14:05", 101, 104, 100, 103, 250),
            ]
        )

        with mock.patch.object(market_data, "get_history", return_value=history):
            image, filename, summary = market_data.build_chart(
                "exm", market_data.RANGES["da"]
            )

        self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertEqual(filename, "exm-1d-5m.png")
        self.assertEqual(summary, "Last: $103.00 | Change: +2.00 (+1.98%) | Trend: up")

    def test_single_intraday_candle_fits_within_its_interval(self) -> None:
        history = _history([("2026-08-07 14:00", 100, 106, 99, 103, 200)])

        for interval, minutes in (("1m", 1), ("5m", 5), ("30m", 30)):
            with self.subTest(interval=interval):
                figure, axes = market_data.plt.subplots(2, 1)
                self.addCleanup(market_data.plt.close, figure)

                market_data._draw_heikin_ashi_candles(axes[0], history, interval)
                market_data._draw_volume(axes[1], history, interval)

                for axis in axes:
                    width = axis.patches[0].get_width()
                    self.assertGreater(width, 0)
                    self.assertLess(width, minutes / (24 * 60))

    def test_chart_without_volume_keeps_visible_time_labels(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 100, 102, 99, 101, 0),
                ("2026-08-07 14:05", 101, 104, 100, 103, 0),
            ]
        )

        for include_volume in (True, False):
            with self.subTest(include_volume=include_volume):
                chart_history = history if include_volume else history.drop(columns="Volume")
                figure, axes = market_data.plt.subplots(2, 1, sharex=True)
                self.addCleanup(market_data.plt.close, figure)
                with (
                    mock.patch.object(market_data, "get_history", return_value=chart_history),
                    mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
                ):
                    market_data.build_chart("EXM", market_data.RANGES["da"])

                self.assertTrue(axes[1].get_visible())
                self.assertTrue(axes[1].xaxis.get_visible())
                self.assertEqual(len(axes[1].get_yticks()), 0)
                self.assertTrue(any(
                    label.get_visible() and label.get_text().strip()
                    for label in axes[1].get_xticklabels()
                ))

    def test_last_price_line_uses_raw_close_instead_of_heikin_ashi_close(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 14:05", 101, 104, 100, 103, 250),
            ]
        )
        raw_close = float(history["Close"].iloc[-1])
        self.assertNotEqual(raw_close, market_data._heikin_ashi(history)["Close"].iloc[-1])
        figure, axes = market_data.plt.subplots(2, 1, sharex=True)
        self.addCleanup(market_data.plt.close, figure)

        with (
            mock.patch.object(market_data, "get_history", return_value=history),
            mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
        ):
            market_data.build_chart("EXM", market_data.RANGES["da"])

        self.assertTrue(any(
            len(line.get_ydata()) >= 2 and all(value == raw_close for value in line.get_ydata())
            for line in axes[0].lines
        ))

    def test_narrow_price_range_keeps_distinct_ticks_and_precise_last_price(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 1.0000, 1.0003, 1.0000, 1.0002, 200),
                ("2026-08-07 14:05", 1.0002, 1.0004, 1.0001, 1.0003, 250),
            ]
        )
        raw_close = float(history["Close"].iloc[-1])
        figure, axes = market_data.plt.subplots(2, 1, sharex=True)
        self.addCleanup(market_data.plt.close, figure)

        with (
            mock.patch.object(market_data, "get_history", return_value=history),
            mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
        ):
            market_data.build_chart("EXM", market_data.RANGES["da"])

        labels = [label.get_text() for label in axes[0].get_yticklabels() if label.get_text()]
        self.assertGreater(len(labels), 1)
        self.assertEqual(len(set(labels)), len(labels))
        badges = [text for text in axes[0].texts if text.get_position()[1] == raw_close]
        self.assertEqual(len(badges), 1)
        self.assertAlmostEqual(float(badges[0].get_text().replace(",", "")), raw_close, places=7)

    def test_crypto_minute_chart_keeps_overnight_history(self) -> None:
        history = _history(
            [
                ("2026-08-08 02:00", 100, 102, 99, 101, 200),
                ("2026-08-08 03:00", 101, 104, 100, 103, 250),
            ]
        )

        with mock.patch.object(market_data, "get_history", return_value=history):
            image, _, summary = market_data.build_chart("BTC-USD", market_data.RANGES["mi"])

        self.assertGreater(len(image.getvalue()), 10_000)
        self.assertNotIn("Market closed", summary)

    def test_format_money_rejects_non_finite_values(self) -> None:
        self.assertEqual(market_data.format_money(math.nan), "n/a")
        self.assertEqual(market_data.format_money(math.inf), "n/a")
