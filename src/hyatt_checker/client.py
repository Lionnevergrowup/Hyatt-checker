from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import quote

from hyatt_checker.hotels import Hotel

log = logging.getLogger(__name__)


# Hyatt's published award chart (standard rooms), effective 2026-05-20.
# Five tiers per category replacing the old off-peak / standard / peak split.
# Order: lowest, low, moderate, upper, top.
TIER_NAMES: tuple[str, ...] = ("lowest", "low", "moderate", "upper", "top")
AWARD_CHART: dict[int, tuple[int, int, int, int, int]] = {
    1: (3_000,  4_500,  6_000,  7_500,  9_000),
    2: (6_000,  7_500, 10_000, 12_000, 15_000),
    3: (8_000, 12_000, 15_000, 17_500, 20_000),
    4: (12_000, 15_000, 20_000, 22_500, 25_000),
    5: (15_000, 20_000, 25_000, 30_000, 35_000),
    6: (20_000, 25_000, 30_000, 35_000, 40_000),
    7: (25_000, 30_000, 35_000, 45_000, 55_000),
    8: (35_000, 45_000, 55_000, 65_000, 75_000),
}


@dataclass(frozen=True)
class NightPrice:
    night: date
    points: int | None  # None == not available on points or fetch failed
    tier: str | None    # "off-peak" | "standard" | "peak" | None


class Fetcher(Protocol):
    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]: ...


class MockFetcher:
    """Generates plausible synthetic pricing from the official award chart.

    No network calls. Useful for development and as a fallback when the
    live fetcher fails for a particular hotel.
    """

    def __init__(self, sellout_chance: float = 0.05) -> None:
        self.sellout_chance = sellout_chance

    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        prices_by_tier = AWARD_CHART[hotel.category]
        # Weekday bias: midweek leans toward cheaper tiers, weekends toward upper.
        weekday_weights = (0.30, 0.30, 0.25, 0.10, 0.05)  # lowest..top
        weekend_weights = (0.05, 0.15, 0.30, 0.30, 0.20)
        out: list[NightPrice] = []
        seed = int(hashlib.sha1(hotel.slug.encode()).hexdigest(), 16)
        cur = start
        i = 0
        while cur < end:
            r = ((seed + i * 2654435761) & 0xFFFF) / 0xFFFF
            if r < self.sellout_chance:
                out.append(NightPrice(cur, None, None))
            else:
                weights = weekend_weights if cur.weekday() >= 5 else weekday_weights
                idx = _weighted_index(r, weights)
                out.append(NightPrice(cur, prices_by_tier[idx], TIER_NAMES[idx]))
            cur += timedelta(days=1)
            i += 1
        return out


def _weighted_index(r: float, weights: tuple[float, ...]) -> int:
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(weights) - 1


class PlaywrightFetcher:
    """Drives a real Chromium browser through Hyatt's award search.

    This intentionally does not call any Hyatt JSON endpoint directly.
    It opens the booking page in a headless browser, lets Hyatt's own JS
    issue the pricing requests, and intercepts the responses. That avoids
    having to guess the API contract, and looks much more like a real
    user to Akamai bot detection than a `curl`.

    Realities to know:
      - Hyatt uses aggressive bot detection. From a datacenter IP this
        may still get blocked; from a residential IP it usually works.
      - The JSON shape returned by Hyatt's internal endpoints changes
        periodically. The parser here is heuristic (walks the response
        tree looking for date/points pairs) so it tolerates small
        renames, but a structural overhaul will break it.
      - Be polite. Default throttle is 4s between requests; default
        chunk size is 30 nights.

    On failure for a given hotel, returns nights with points=None so
    the calendar renders the dates as "tap to check" instead of crashing
    the whole run.
    """

    SEARCH_URL = "https://www.hyatt.com/search/hotels?q={q}"
    SHOP_URL = (
        "https://www.hyatt.com/shop/rooms/{code}"
        "?checkinDate={checkin}&checkoutDate={checkout}"
        "&rooms=1&adults=1&rate=woh"
    )
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # Inlined puppeteer-stealth-style patches. Far from bullet-proof against
    # Akamai, but covers the cheap detection surface (navigator.webdriver,
    # missing chrome.runtime, plugin list, languages, permissions API).
    STEALTH_JS = """
      Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
      window.chrome = window.chrome || { runtime: {} };
      Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
      Object.defineProperty(navigator,'plugins',{
        get:()=>[{name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'},{name:'Native Client'}]
      });
      const _q = (window.navigator.permissions||{}).query;
      if (_q) {
        window.navigator.permissions.query = (p) =>
          p && p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _q.call(window.navigator.permissions, p);
      }
      Object.defineProperty(screen,'colorDepth',{get:()=>24});
    """
    EXTRA_HEADERS = {
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(
        self,
        headless: bool = True,
        throttle_s: float = 4.0,
        chunk_days: int = 30,
        nav_timeout_ms: int = 30_000,
        debug_dir: Path | None = None,
    ) -> None:
        self.headless = headless
        self.throttle_s = throttle_s
        self.chunk_days = chunk_days
        self.nav_timeout_ms = nav_timeout_ms
        self.debug_dir = debug_dir
        self._debug_dumped = False

    def fetch(self, hotel: Hotel, start: date, end: date) -> list[NightPrice]:
        from playwright.sync_api import sync_playwright  # lazy import

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            ctx = browser.new_context(
                user_agent=self.USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers=self.EXTRA_HEADERS,
            )
            ctx.add_init_script(self.STEALTH_JS)
            page = ctx.new_page()
            page.set_default_timeout(self.nav_timeout_ms)

            try:
                code = hotel.code or self._discover_code(page, hotel)
                if not code:
                    log.warning("no property code for %s; returning blanks", hotel.name)
                    self._dump_debug(page, hotel, "no-code")
                    return _blank_window(start, end)
                if code != hotel.code:
                    log.info("discovered code %s for %s", code, hotel.name)
                    hotel = replace(hotel, code=code)

                results: list[NightPrice] = []
                cur = start
                while cur < end:
                    chunk_end = min(cur + timedelta(days=self.chunk_days), end)
                    results.extend(self._fetch_chunk(page, hotel, cur, chunk_end))
                    cur = chunk_end
                    time.sleep(self.throttle_s)
                # If we got nothing useful, dump a snapshot of the last page
                # so we can see what Hyatt actually returned.
                if not any(r.points for r in results):
                    self._dump_debug(page, hotel, "no-prices")
                return results
            except Exception as e:
                log.warning("PlaywrightFetcher failed for %s: %s", hotel.name, e)
                self._dump_debug(page, hotel, "exception")
                return _blank_window(start, end)
            finally:
                browser.close()

    def _dump_debug(self, page, hotel: Hotel, tag: str) -> None:
        """Save a screenshot + html of the current page once per run.

        Only writes for the first hotel that triggers a dump, so we don't
        produce 28 megabytes of nearly-identical debug bundles every run.
        """
        if not self.debug_dir or self._debug_dumped:
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            base = self.debug_dir / f"first-failure-{tag}-{hotel.slug}"
            page.screenshot(path=str(base.with_suffix(".png")), full_page=False)
            (base.with_suffix(".html")).write_text(page.content(), encoding="utf-8")
            (base.with_suffix(".url")).write_text(page.url, encoding="utf-8")
            log.info("wrote debug bundle: %s.*", base)
            self._debug_dumped = True
        except Exception as e:
            log.debug("debug dump failed: %s", e)

    def _discover_code(self, page, hotel: Hotel) -> str | None:
        url = self.SEARCH_URL.format(q=quote(hotel.name))
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception as e:
            log.debug("search nav failed for %s: %s", hotel.name, e)
            return None
        html = page.content()
        # Hotel shop URLs look like /shop/<code> or /shop/rooms/<code>.
        # Codes are typically 5 lowercase letters/digits.
        m = re.search(r'/shop/(?:rooms/)?([a-z0-9]{4,8})', html)
        return m.group(1) if m else None

    def _fetch_chunk(
        self, page, hotel: Hotel, start: date, end: date
    ) -> list[NightPrice]:
        assert hotel.code is not None
        captured: list[object] = []

        def on_response(resp):
            ct = (resp.headers or {}).get("content-type", "")
            if "json" not in ct:
                return
            url = resp.url.lower()
            if not any(k in url for k in ("pricing", "availability", "rate", "shop")):
                return
            try:
                captured.append(resp.json())
            except Exception:
                pass

        page.on("response", on_response)
        url = self.SHOP_URL.format(
            code=hotel.code,
            checkin=start.isoformat(),
            checkout=end.isoformat(),
        )
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception as e:
            log.debug("chunk nav failed %s %s: %s", hotel.name, start, e)
        finally:
            page.remove_listener("response", on_response)

        return _parse_captured(captured, hotel, start, end)


def _blank_window(start: date, end: date) -> list[NightPrice]:
    out: list[NightPrice] = []
    cur = start
    while cur < end:
        out.append(NightPrice(cur, None, None))
        cur += timedelta(days=1)
    return out


def _parse_captured(
    captured: list[object], hotel: Hotel, start: date, end: date
) -> list[NightPrice]:
    """Walk every captured JSON response for (date, points) pairs."""
    nights: dict[date, int] = {}
    for blob in captured:
        for d, pts in _walk_for_date_points(blob):
            if start <= d < end and pts > 0:
                nights[d] = min(nights.get(d, pts), pts)
    return [
        NightPrice(
            night=d,
            points=nights.get(d),
            tier=_infer_tier(hotel, nights.get(d)),
        )
        for d in _daterange(start, end)
    ]


def _daterange(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur < end:
        yield cur
        cur += timedelta(days=1)


_DATE_KEYS = ("date", "checkindate", "checkin", "stayDate", "stay_date", "day")
_POINTS_KEYS = (
    "points", "pointsamount", "pointsprice", "pointsrate",
    "amount", "value", "rate",
)


def _walk_for_date_points(obj) -> Iterable[tuple[date, int]]:
    if isinstance(obj, dict):
        date_v = None
        pts_v = None
        for k, v in obj.items():
            lk = k.lower()
            if date_v is None and lk in _DATE_KEYS and isinstance(v, str):
                date_v = v
            elif pts_v is None and lk in _POINTS_KEYS and isinstance(v, (int, float)):
                pts_v = int(v)
        if date_v and pts_v and pts_v >= 1_000:
            try:
                yield (date.fromisoformat(date_v[:10]), pts_v)
            except ValueError:
                pass
        for v in obj.values():
            yield from _walk_for_date_points(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_for_date_points(v)


def _infer_tier(hotel: Hotel, points: int | None) -> str | None:
    if points is None:
        return None
    chart = AWARD_CHART.get(hotel.category)
    if not chart:
        return None
    # Find the tier whose published price is closest to the observed points;
    # tolerates small server-side variations and clamps out-of-range values
    # to the nearest endpoint tier.
    best_i = 0
    best_diff = abs(points - chart[0])
    for i, p in enumerate(chart):
        diff = abs(points - p)
        if diff < best_diff:
            best_diff = diff
            best_i = i
    return TIER_NAMES[best_i]


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
