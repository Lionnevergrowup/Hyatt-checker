from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from hyatt_checker.client import CachingFetcher, Fetcher, MockFetcher, PlaywrightFetcher
from hyatt_checker.hotels import Hotel, filter_us_cat_1_2, load_hotels
from hyatt_checker.report import build_report, render_html, write_report

DEFAULT_HOTELS = Path("data/hotels.json")
DEFAULT_OUTPUT = Path("output/report.html")
DEFAULT_CACHE = Path(".cache")
SNAPSHOT_NAME = "snapshot.json"


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
    p.add_argument("--discover", action="store_true",
                   help="Before fetching, try to refresh data/hotels.json by scraping "
                        "Hyatt's hotel directory via Playwright. Best-effort: keeps "
                        "the existing list if discovery fails or finds nothing.")
    p.add_argument("--favorites", type=Path, default=None,
                   help="Optional file with one hotel slug or substring per line; "
                        "only matching hotels appear in the report.")
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


def apply_favorites(hotels: list[Hotel], favorites_path: Path | None) -> list[Hotel]:
    if favorites_path is None or not favorites_path.exists():
        return hotels
    needles = [
        line.strip().lower()
        for line in favorites_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not needles:
        return hotels
    return [
        h for h in hotels
        if any(n in h.slug.lower() or n in h.name.lower() for n in needles)
    ]


def load_snapshot(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_snapshot(path: Path, reports) -> None:
    snap: dict[str, dict[str, int]] = {}
    for r in reports:
        per_day: dict[str, int] = {}
        for m in r.months:
            for week in m.weeks:
                for cell in week:
                    if cell and cell.points:
                        d = date(m.year, m.month, cell.day).isoformat()
                        per_day[d] = cell.points
        if per_day:
            snap[r.hotel.slug] = per_day
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("hyatt_checker")

    if args.discover:
        try:
            from hyatt_checker.discover import discover_us_cat_1_2, merge_into_file
            found = discover_us_cat_1_2()
            if found:
                added, updated = merge_into_file(found, args.hotels)
                log.info("discovery merged into %s (+%d new, %d updated)", args.hotels, added, updated)
            else:
                log.warning("discovery returned 0 hotels; keeping existing %s", args.hotels)
        except Exception as e:
            log.warning("discovery failed: %s; keeping existing %s", e, args.hotels)

    hotels = filter_us_cat_1_2(load_hotels(args.hotels))
    hotels = apply_favorites(hotels, args.favorites)
    log.info("loaded %d Cat 1/2 US hotels", len(hotels))

    start = date.today()
    end = _add_months(start, args.months)
    log.info("window: %s -> %s", start, end)

    fetcher = build_fetcher(args.source, None if args.no_cache else args.cache_dir)

    snapshot_path = args.cache_dir / SNAPSHOT_NAME
    previous = load_snapshot(snapshot_path)
    if previous:
        log.info("loaded previous snapshot with %d hotels for diff", len(previous))

    reports = []
    for hotel in hotels:
        log.info("fetching %s (cat %d)", hotel.name, hotel.category)
        prices = fetcher.fetch(hotel, start, end)
        reports.append(build_report(hotel, prices, start, end, previous=previous.get(hotel.slug)))

    html = render_html(
        reports,
        start,
        end,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        source=args.source,
    )
    write_report(html, args.output)
    save_snapshot(snapshot_path, reports)
    log.info("wrote %s", args.output)
    return 0


def _add_months(d: date, months: int) -> date:
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
