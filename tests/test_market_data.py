from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
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


def _volume_history(volumes: list[int]) -> pd.DataFrame:
    start = datetime(2026, 8, 7, 14, tzinfo=timezone.utc)
    return _history([
        ((start + timedelta(minutes=5 * index)).isoformat(), 100, 104, 99, 103, volume)
        for index, volume in enumerate(volumes)
    ])


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

    def test_single_day_history_keeps_requested_date_and_extended_hours(self) -> None:
        history = _history(
            [
                ("2026-08-06 14:00", 90, 92, 89, 91, 100),
                ("2026-08-07 11:55", 97, 98, 96, 97, 10),
                ("2026-08-07 12:00", 98, 99, 97, 98, 20),
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 21:00", 103, 104, 102, 103, 30),
                ("2026-08-08 00:05", 104, 105, 103, 104, 10),
            ]
        )

        result = market_data._single_day_history(history, date(2026, 8, 7))

        self.assertFalse(result.attrs.get("flat_closed_session", False))
        self.assertEqual(result["Close"].tolist(), [98, 101, 103])

    def test_closed_day_creates_flat_line_for_requested_date(self) -> None:
        history = _history(
            [
                ("2026-08-07 14:00", 100, 102, 99, 101, 200),
                ("2026-08-07 21:00", 103, 104, 102, 103, 30),
            ]
        )

        result = market_data._single_day_history(history, date(2026, 8, 8))

        self.assertTrue(result.attrs["flat_closed_session"])
        self.assertEqual(len(result), 79)
        self.assertEqual(result.index[0].date(), date(2026, 8, 8))
        self.assertTrue((result["Close"] == 103).all())
        self.assertEqual(result["Volume"].sum(), 0)

    def test_single_day_stock_charts_shade_extended_sessions_with_dst(self) -> None:
        for earlier_day, latest_day, utc_open_hour in (
            (date(2026, 1, 8), date(2026, 1, 9), 13),
            (date(2026, 8, 6), date(2026, 8, 7), 12),
        ):
            history = _history([
                (datetime(day.year, day.month, day.day, hour,
                          tzinfo=market_data.MARKET_TZ).isoformat(),
                 close - 1, close + 2, close - 2, close, 100)
                for day in (earlier_day, latest_day)
                for hour, close in ((8, 98), (10, 101), (17, 103))
            ])
            for range_key in ("mi", "da"):
                with self.subTest(month=earlier_day.month, range=range_key):
                    target_day = earlier_day if range_key == "mi" else latest_day
                    today = earlier_day if range_key == "mi" else latest_day + timedelta(days=1)
                    figure, axes = market_data.plt.subplots(2, 1, sharex=True)
                    self.addCleanup(market_data.plt.close, figure)
                    with (
                        mock.patch.object(market_data, "get_history", return_value=history),
                        mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
                        mock.patch.object(market_data, "datetime", wraps=datetime) as frozen_datetime,
                    ):
                        frozen_datetime.now.return_value = datetime(
                            today.year, today.month, today.day, 12, tzinfo=market_data.MARKET_TZ
                        )
                        _, _, summary = market_data.build_chart("EXM", market_data.RANGES[range_key])

                    opening = datetime(target_day.year, target_day.month, target_day.day,
                                       utc_open_hour, tzinfo=timezone.utc)
                    expected_spans = [
                        (opening, opening + timedelta(hours=1, minutes=30)),
                        (opening + timedelta(hours=8), opening + timedelta(hours=12)),
                    ]
                    for axis in axes:
                        spans = [patch for patch in axis.patches
                                 if patch.get_data_transform() == axis.get_xaxis_transform()]
                        self.assertEqual(len(spans), 2)
                        for span, (start, end) in zip(spans, expected_spans):
                            self.assertAlmostEqual(span.get_x(), market_data.mdates.date2num(start))
                            self.assertAlmostEqual(span.get_x() + span.get_width(),
                                                   market_data.mdates.date2num(end))
                        self.assertEqual(axis.get_xlim(), (
                            market_data.mdates.date2num(opening),
                            market_data.mdates.date2num(opening + timedelta(hours=12)),
                        ))
                    self.assertNotIn("Market closed", summary)

    def test_premarket_only_history_uses_real_candles(self) -> None:
        history = _history([
            ("2026-08-07 12:00", 98, 102, 97, 100, 20),
            ("2026-08-07 12:05", 100, 104, 99, 103, 30),
        ])

        selected = market_data._single_day_history(history, date(2026, 8, 7))

        self.assertFalse(selected.attrs.get("flat_closed_session", False))
        pd.testing.assert_frame_equal(selected, history)
        figure, axes = market_data.plt.subplots(2, 1, sharex=True)
        self.addCleanup(market_data.plt.close, figure)
        with (
            mock.patch.object(market_data, "get_history", return_value=history),
            mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
        ):
            _, _, summary = market_data.build_chart("EXM", market_data.RANGES["da"])

        candle_bodies = [patch for patch in axes[0].patches
                         if patch.get_data_transform() == axes[0].transData]
        self.assertEqual(len(candle_bodies), len(history))
        self.assertNotIn("Market closed", summary)
        self.assertIn("Last: $103.00", summary)

    def test_crypto_and_multiday_charts_have_no_stock_session_shading(self) -> None:
        history = _history([
            ("2026-08-06 02:00", 98, 101, 97, 100, 20),
            ("2026-08-07 14:00", 100, 104, 99, 103, 30),
        ])

        for symbol, range_key in (("BTC-USD", "mi"), ("BTC-USD", "da"),
                                  ("EXM", "we"), ("EXM", "mo")):
            with self.subTest(symbol=symbol, range=range_key):
                figure, axes = market_data.plt.subplots(2, 1, sharex=True)
                self.addCleanup(market_data.plt.close, figure)
                with (
                    mock.patch.object(market_data, "get_history", return_value=history),
                    mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
                ):
                    market_data.build_chart(symbol, market_data.RANGES[range_key])

                for axis in axes:
                    spans = [patch for patch in axis.patches
                             if patch.get_data_transform() == axis.get_xaxis_transform()]
                    self.assertEqual(spans, [])
                    left, right = axis.get_xlim()
                    self.assertLess(left, market_data.mdates.date2num(history.index[0]))
                    self.assertGreater(right, market_data.mdates.date2num(history.index[-1]))

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
                candle_time = market_data.mdates.date2num(history.index[0])
                for axis in axes:
                    axis.set_xlim(candle_time - minutes / 1440, candle_time + minutes / 1440)

                market_data._draw_heikin_ashi_candles(axes[0], history, interval)
                market_data._set_volume_ylim(axes[1], history)
                market_data._draw_volume(axes[1], history, interval)

                width = axes[0].patches[0].get_width()
                self.assertGreater(width, 0)
                self.assertLess(width, minutes / (24 * 60))
                volume = axes[1].collections[0]
                self.assertEqual(len(volume.get_segments()), 1)
                left = axes[1].transData.transform((candle_time, 0))[0]
                right = axes[1].transData.transform((candle_time + width, 0))[0]
                candle_width_points = (right - left) * 72 / figure.dpi
                self.assertGreater(volume.get_linewidths()[0], 0)
                self.assertLess(volume.get_linewidths()[0], candle_width_points)

    def test_isolated_volume_spike_caps_view_but_keeps_real_volume(self) -> None:
        volumes = [100_000 + index * 10_000 for index in range(24)] + [21_000_000]
        history = _volume_history(volumes)
        original = history.copy(deep=True)
        figure, axes = market_data.plt.subplots(2, 1, sharex=True)
        self.addCleanup(market_data.plt.close, figure)

        with (
            mock.patch.object(market_data, "get_history", return_value=history),
            mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
        ):
            market_data.build_chart("MRNA", market_data.RANGES["da"])

        self.assertAlmostEqual(axes[1].get_ylim()[1], sorted(volumes)[-2] * 1.25)
        segments = axes[1].collections[0].get_segments()
        self.assertEqual([segment[1, 1] for segment in segments], volumes)
        self.assertTrue(all(segment[0, 1] == 0 for segment in segments))
        pd.testing.assert_frame_equal(history, original)
        labels = [text.get_text() for text in axes[1].texts]
        self.assertIn("21.0M", labels)
        self.assertIn("//", labels)
        self.assertTrue(any("clipped" in label.lower() for label in labels))

    def test_chart_header_reports_raw_ohlc_and_total_volume_including_clipped_spike(self) -> None:
        history = _volume_history([100_000] * 24 + [21_000_000])
        history.iloc[10, history.columns.get_loc("High")] = 115
        history.iloc[15, history.columns.get_loc("Low")] = 95
        history.iloc[-1, history.columns.get_loc("Close")] = 102
        figure, axes = market_data.plt.subplots(2, 1, sharex=True)
        self.addCleanup(market_data.plt.close, figure)

        with (
            mock.patch.object(market_data, "get_history", return_value=history),
            mock.patch.object(market_data.plt, "subplots", return_value=(figure, axes)),
        ):
            market_data.build_chart("MRNA", market_data.RANGES["da"])

        header = next(text.get_text() for text in figure.texts if "Vol:" in text.get_text())
        values = {key: float(value.replace(",", ""))
                  for key, value in re.findall(r"\b(O|H|L|C):\s*([\d,.]+)", header)}
        self.assertEqual(values, {"O": 100, "H": 115, "L": 95, "C": 102})
        self.assertNotEqual(values["C"], market_data._heikin_ashi(history)["Close"].iloc[-1])
        self.assertIn("Vol: 23.4M", header)
        self.assertLess(axes[1].get_ylim()[1], history["Volume"].max())

    def test_chart_header_distinguishes_missing_volume_from_zero(self) -> None:
        history = _volume_history([0, 0])
        for chart_history, expected in (
            (history.drop(columns="Volume"), "—"),
            (history.assign(Volume=math.nan), "—"),
            (history, "0"),
        ):
            with self.subTest(expected=expected, columns=chart_history.columns.tolist()):
                figure = market_data.plt.figure()
                self.addCleanup(market_data.plt.close, figure)
                market_data._draw_chart_header(
                    figure, "EXM", market_data.RANGES["da"], chart_history, 0, 0
                )

                header = next(text.get_text() for text in figure.texts if "Vol:" in text.get_text())
                self.assertEqual(re.search(r"Vol:\s*(\S+)", header).group(1), expected)

    def test_closed_day_header_reports_carried_price_without_invented_ohlc(self) -> None:
        history = _volume_history([100, 200])
        closed_history = market_data._single_day_history(history, date(2026, 8, 8))
        figure = market_data.plt.figure()
        self.addCleanup(market_data.plt.close, figure)

        market_data._draw_chart_header(
            figure, "EXM", market_data.RANGES["mi"], closed_history, 0, 0
        )

        texts = "\n".join(text.get_text() for text in figure.texts)
        self.assertTrue(closed_history.attrs["flat_closed_session"])
        self.assertEqual(float(re.search(r"Last:\s*([\d,.]+)", texts).group(1)), 103)
        for field in ("O:", "H:", "L:", "C:", "Vol:"):
            self.assertNotIn(field, texts)
        self.assertIn("Market closed", texts)
        self.assertIn("carry-forward price", texts)

    def test_broad_volume_surge_keeps_full_scale(self) -> None:
        for peaks in ([21_000_000, 18_000_000], [21_000_000, 21_000_000]):
            with self.subTest(peaks=peaks):
                history = _volume_history([100_000] * 24 + list(peaks))
                figure, axis = market_data.plt.subplots()
                self.addCleanup(market_data.plt.close, figure)
                market_data._set_volume_ylim(axis, history)
                market_data._draw_volume(axis, history, "5m")

                self.assertAlmostEqual(axis.get_ylim()[1], max(peaks) * 1.18)
                self.assertFalse(any("clipped" in text.get_text().lower() for text in axis.texts))

    def test_sparse_positive_volume_keeps_full_scale_and_omits_zero_bars(self) -> None:
        for volumes in (
            [100_000] * 18 + [21_000_000],
            [0] * 50 + [100_000, 21_000_000],
            [0] * 30 + [21_000_000] + [0] * 20,
        ):
            with self.subTest(positive_count=sum(volume > 0 for volume in volumes)):
                history = _volume_history(volumes)
                figure, axis = market_data.plt.subplots()
                self.addCleanup(market_data.plt.close, figure)
                market_data._set_volume_ylim(axis, history)
                market_data._draw_volume(axis, history, "5m")

                self.assertAlmostEqual(axis.get_ylim()[1], max(volumes) * 1.18)
                segments = axis.collections[0].get_segments()
                self.assertEqual([segment[1, 1] for segment in segments],
                                 [volume for volume in volumes if volume > 0])
                self.assertFalse(any("clipped" in text.get_text().lower() for text in axis.texts))

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
