"""Best-effort discovery of all US Cat 1 & 2 Hyatt properties.

Hyatt rebalances categories twice a year, so a hand-maintained list goes
stale. This module drives a real browser through Hyatt's hotel search,
intercepts the JSON the page loads, and walks it for property records
that look like Cat 1 or Cat 2 US hotels.

It is best-effort: if Akamai blocks the request, or Hyatt restructures
their response, discovery returns an empty list and the caller should
fall back to the existing hand-curated file.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Iterable

from hyatt_checker.hotels import Hotel

log = logging.getLogger(__name__)


# Hyatt's directory search. The page renders client-side from a JSON
# payload that we intercept rather than parsing the rendered DOM.
SEARCH_URLS = [
    "https://www.hyatt.com/search/hotels?country=US&pageSize=500",
    "https://www.hyatt.com/explore-hotels/services/hotels?country=US&pageSize=500",
]


def discover_us_cat_1_2(headless: bool = True, timeout_ms: int = 30_000) -> list[Hotel]:
    from playwright.sync_api import sync_playwright

    captured: list[object] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = ctx.new_page()
        page.set_default_timeout(timeout_ms)

        def on_response(resp):
            ct = (resp.headers or {}).get("content-type", "")
            if "json" not in ct:
                return
            url = resp.url.lower()
            if not any(k in url for k in ("hotel", "search", "explore", "propert")):
                return
            try:
                captured.append(resp.json())
            except Exception:
                pass

        page.on("response", on_response)
        for url in SEARCH_URLS:
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception as e:
                log.debug("discovery nav failed for %s: %s", url, e)
        browser.close()

    hotels = list(_walk_for_hotels(captured))
    # Dedupe by slug
    seen: dict[str, Hotel] = {}
    for h in hotels:
        if h.country != "US" or h.category not in (1, 2):
            continue
        seen.setdefault(h.slug, h)
    found = list(seen.values())
    log.info("discovery found %d US Cat 1/2 candidates", len(found))
    return sorted(found, key=lambda h: (h.category, h.state, h.name))


_NAME_KEYS = ("name", "hotelName", "displayName", "title")
_CATEGORY_KEYS = ("category", "categoryId", "categoryNumber", "awardCategory")
_COUNTRY_KEYS = ("country", "countryCode", "countryName")
_STATE_KEYS = ("state", "stateCode", "stateProvince", "region")
_CITY_KEYS = ("city", "cityName", "locality")
_CODE_KEYS = ("code", "spiritCode", "propertyCode", "hotelCode", "id")


def _walk_for_hotels(obj) -> Iterable[Hotel]:
    if isinstance(obj, dict):
        candidate = _maybe_hotel(obj)
        if candidate is not None:
            yield candidate
        for v in obj.values():
            yield from _walk_for_hotels(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_for_hotels(v)


def _maybe_hotel(d: dict) -> Hotel | None:
    name = _first_str(d, _NAME_KEYS)
    category = _first_int(d, _CATEGORY_KEYS)
    country = _first_str(d, _COUNTRY_KEYS) or _nested_str(d, ("address",), _COUNTRY_KEYS)
    if not (name and category and country):
        return None
    if not (1 <= category <= 8):
        return None
    # Hyatt's name field is usually "Hyatt Place X" / "Hyatt Regency Y" etc.
    if not re.search(r"\bhyatt\b|caption|andaz|alila|miraval|thompson", name, re.I):
        return None
    state = (
        _first_str(d, _STATE_KEYS)
        or _nested_str(d, ("address",), _STATE_KEYS)
        or ""
    )
    city = (
        _first_str(d, _CITY_KEYS)
        or _nested_str(d, ("address",), _CITY_KEYS)
        or ""
    )
    code = _first_str(d, _CODE_KEYS)
    country_norm = "US" if country.upper() in ("US", "USA", "UNITED STATES") else country.upper()
    return Hotel(
        code=code,
        name=name,
        category=category,
        city=city,
        state=state,
        country=country_norm,
    )


def _first_str(d: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first_int(d: dict, keys: tuple[str, ...]) -> int | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and 1 <= int(v) <= 8:
            return int(v)
        if isinstance(v, str) and v.isdigit() and 1 <= int(v) <= 8:
            return int(v)
    return None


def _nested_str(d: dict, parents: tuple[str, ...], keys: tuple[str, ...]) -> str | None:
    cur = d
    for p in parents:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    if not isinstance(cur, dict):
        return None
    return _first_str(cur, keys)


def merge_into_file(found: list[Hotel], path: Path) -> tuple[int, int]:
    """Merge discovered hotels into hotels.json, returning (added, updated)."""
    existing: list[dict] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    )
    by_slug: dict[str, dict] = {}
    for entry in existing:
        slug = (entry.get("code") or entry.get("name", "")).lower().replace(" ", "-").replace("/", "-")
        by_slug[slug] = entry

    added = 0
    updated = 0
    today = date.today().isoformat()
    for h in found:
        entry = {
            "code": h.code,
            "name": h.name,
            "category": h.category,
            "city": h.city,
            "state": h.state,
            "country": h.country,
        }
        if h.slug in by_slug:
            old = by_slug[h.slug]
            # Update category and code if discovered ones are populated
            changed = False
            if h.code and old.get("code") != h.code:
                old["code"] = h.code
                changed = True
            if h.category and old.get("category") != h.category:
                old["category"] = h.category
                changed = True
            if changed:
                updated += 1
        else:
            by_slug[h.slug] = entry
            added += 1

    out = sorted(by_slug.values(), key=lambda e: (e.get("category", 99), e.get("state", ""), e.get("name", "")))
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    log.info("merged into %s: +%d new, %d updated (total %d), at %s", path, added, updated, len(out), today)
    return added, updated
