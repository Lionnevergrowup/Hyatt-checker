from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

import httpx

from hyatt_checker.hotels import Hotel

log = logging.getLogger(__name__)


# Hyatt's published award chart (standard rooms). Off-peak / standard / peak.
AWARD_CHART: dict[int, tuple[int, int, int]] = {
    1: (3_500, 5_000, 6_500),
    2: (6_500, 8_000, 9_500),
    3: (9_000, 12_000, 15_000),
    4: (12_000, 15_000, 18_000),
    5: (17_000, 20_000, 23_000),
    6: (21_000, 25_000, 29_000),
    7: (25_000, 30_000, 35_000),
    8: (35_000, 40_000, 45_000),
}


@dataclass(frozen=True)
class NightPrice:
    night: date
    points: int | None  # None == not available on points
    tier: str | None    # "off-peak" | "standard" | "peak" | None


class Fetcher(Protocol):
    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]: ...


class MockFetcher:
    """Generates plausible synthetic pricing using the official award chart.

    Useful for offline development and for verifying the report pipeline
    without hitting Hyatt's servers. Replace with LiveFetcher for real data.
    """

    def __init__(self, sellout_chance: float = 0.05) -> None:
        self.sellout_chance = sellout_chance

    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        off_peak, standard, peak = AWARD_CHART[hotel.category]
        out: list[NightPrice] = []
        seed = int(hashlib.sha1(hotel.slug.encode()).hexdigest(), 16)
        cur = start
        i = 0
        while cur < end:
            r = ((seed + i * 2654435761) & 0xFFFF) / 0xFFFF
            if r < self.sellout_chance:
                out.append(NightPrice(cur, None, None))
            elif cur.weekday() >= 5:  # Sat/Sun lean peak
                tier = "peak" if r < 0.4 else "standard"
                out.append(NightPrice(cur, peak if tier == "peak" else standard, tier))
            else:
                tier = "off-peak" if r < 0.5 else "standard"
                out.append(
                    NightPrice(cur, off_peak if tier == "off-peak" else standard, tier)
                )
            cur += timedelta(days=1)
            i += 1
        return out


class LiveFetcher:
    """Skeleton for a real Hyatt fetcher.

    Hyatt has no public API. Their site uses anti-bot tokens and rotating
    session cookies, and the request shape changes periodically. To finish
    this implementation you need to:

      1. Open the Hyatt award search in a browser with devtools open.
      2. Capture the JSON endpoint it calls (something under www.hyatt.com
         that returns nightly point pricing for a property + date range).
      3. Fill in _fetch_one below: build the request, parse the response,
         and map each night to a NightPrice. Determine the tier from the
         returned points by comparing against AWARD_CHART[hotel.category].
      4. Keep the throttle conservative (the defaults below are a starting
         point). Cache results aggressively via CachingFetcher.
    """

    BASE_URL = "https://www.hyatt.com"  # TODO: replace with real pricing endpoint
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )

    def __init__(self, request_delay_s: float = 2.0, chunk_days: int = 30) -> None:
        self.request_delay_s = request_delay_s
        self.chunk_days = chunk_days
        self._client = httpx.Client(
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            timeout=20.0,
        )

    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        if not hotel.code:
            log.warning("skipping %s: no property code", hotel.name)
            return []
        out: list[NightPrice] = []
        cur = start
        while cur < end:
            chunk_end = min(cur + timedelta(days=self.chunk_days), end)
            out.extend(self._fetch_one(hotel, cur, chunk_end))
            cur = chunk_end
            time.sleep(self.request_delay_s)
        return out

    def _fetch_one(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        # TODO: implement the real request once the endpoint is known.
        # Example shape (do not assume this URL is correct):
        #   GET {BASE_URL}/shop/pricing/{hotel.code}
        #       ?checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&rate=woh
        raise NotImplementedError(
            "LiveFetcher is a skeleton. Capture the real Hyatt pricing endpoint "
            "and implement _fetch_one. See module docstring for details."
        )


class CachingFetcher:
    """Wraps another fetcher with an on-disk JSON cache keyed by hotel+window."""

    def __init__(self, inner: Fetcher, cache_dir: Path) -> None:
        self.inner = inner
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        key = f"{hotel.slug}_{start.isoformat()}_{end.isoformat()}.json"
        cache_path = self.cache_dir / key
        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return [
                NightPrice(date.fromisoformat(d["night"]), d["points"], d["tier"])
                for d in data
            ]
        prices = self.inner.fetch(hotel, start, end)
        cache_path.write_text(
            json.dumps(
                [
                    {"night": p.night.isoformat(), "points": p.points, "tier": p.tier}
                    for p in prices
                ]
            ),
            encoding="utf-8",
        )
        return prices
