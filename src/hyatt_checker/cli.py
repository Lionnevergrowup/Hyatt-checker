from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from hyatt_checker.client import CachingFetcher, Fetcher, MockFetcher, PlaywrightFetcher
from hyatt_checker.hotels import filter_us_cat_1_2, load_hotels
from hyatt_checker.report import build_report, render_html, write_report

DEFAULT_HOTELS = Path("data/hotels.json")
DEFAULT_OUTPUT = Path("output/report.html")
DEFAULT_CACHE = Path(".cache")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="hyatt-checker",
        description="Generate a 6-month award pricing report for US Cat 1 & 2 Hyatts.",
    )
    p.add_argument("--hotels", type=Path, default=DEFAULT_HOTELS,
                   help="JSON file listing properties (default: data/hotels.json).")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help="Where to write the HTML report.")
    p.add_argument("--months", type=int, default=6,
                   help="How many months ahead to check (default: 6).")
    p.add_argument("--source", choices=("mock", "live"), default="mock",
                   help="'mock' = synthetic pricing from the award chart (no network). "
                        "'live' = drive a real Chromium browser via Playwright "
                        "(install with `pip install -e .[live] && playwright install chromium`).")
    p.add_argument("--no-cache", action="store_true",
                   help="Disable the on-disk pricing cache.")
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def build_fetcher(source: str, cache_dir: Path | None) -> Fetcher:
    base: Fetcher = MockFetcher() if source == "mock" else PlaywrightFetcher()
    if cache_dir is None:
        return base
    return CachingFetcher(base, cache_dir)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("hyatt_checker")

    hotels = filter_us_cat_1_2(load_hotels(args.hotels))
    log.info("loaded %d Cat 1/2 US hotels", len(hotels))

    start = date.today()
    end = _add_months(start, args.months)
    log.info("window: %s -> %s", start, end)

    fetcher = build_fetcher(args.source, None if args.no_cache else args.cache_dir)

    reports = []
    for hotel in hotels:
        log.info("fetching %s (cat %d)", hotel.name, hotel.category)
        prices = fetcher.fetch(hotel, start, end)
        reports.append(build_report(hotel, prices, start, end))

    html = render_html(
        reports,
        start,
        end,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        source=args.source,
    )
    write_report(html, args.output)
    log.info("wrote %s", args.output)
    return 0


def _add_months(d: date, months: int) -> date:
    # End-exclusive: same day-of-month N months later, clamped.
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return (next_first - timedelta(days=1)).day
