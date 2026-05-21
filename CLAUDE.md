# CLAUDE.md

Guidance for AI assistants (Claude Code and similar tools) working in this repository.

## Project Overview

**Name:** Hyatt-checker

**Purpose:** Generate a 6-month award-pricing report for Category 1 & 2 World of
Hyatt hotels in the United States. Output is a single mobile-friendly HTML page
with one section per hotel and a month-by-month calendar showing the points
cost for every night, color-coded off-peak / standard / peak. Every cell is a
tappable deeplink to Hyatt's award search for that night.

**Primary use case:** GitHub Actions runs the checker weekly (and on demand
via `workflow_dispatch`), publishes the result to GitHub Pages, and the user
opens the page from a phone bookmark.

## Repository Structure

```
.
├── .github/workflows/weekly.yml # scheduled + manual job, publishes to GH Pages
├── data/
│   └── hotels.json              # curated US Cat 1 & 2 properties
├── src/hyatt_checker/
│   ├── __init__.py
│   ├── __main__.py              # `python -m hyatt_checker` entry
│   ├── cli.py                   # argparse entry point (hyatt-checker)
│   ├── hotels.py                # Hotel dataclass + JSON loader / filter
│   ├── client.py                # Fetcher protocol + Mock / Playwright / Caching + award chart
│   └── report.py                # Jinja2 HTML calendar + Hyatt deeplinks
├── output/                      # generated reports (gitignored)
├── .cache/                      # on-disk pricing cache (gitignored)
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

## Tech Stack

- **Language & runtime:** Python 3.11+
- **Package manager:** `pip` (project uses `pyproject.toml` with hatchling)
- **Key libraries:**
  - `httpx` — HTTP client (currently only a transitive dep, kept for future use)
  - `jinja2` — HTML templating
  - `playwright` — headless Chromium for the live fetcher (optional `[live]` extra)
- **Storage:** JSON files (hotel list + cached pricing). No database.
- **Hosting:** GitHub Actions on a weekly cron, deployed to GitHub Pages.

## Development Workflow

```bash
# install (mock only — no browser)
pip install -e .

# generate report with synthetic data — no network calls
hyatt-checker --source mock --output output/report.html -v

# install live fetcher + drive a real browser
pip install -e ".[live]"
playwright install chromium
hyatt-checker --source live --output output/report.html -v
```

There are no tests yet. There is no linter/formatter configured yet. Add
`ruff` when the codebase grows.

## Architecture

The pipeline is small and linear:

1. `cli.main` loads `data/hotels.json` and filters to `country=US` and
   `category in {1, 2}`.
2. For each hotel it asks a `Fetcher` for nightly point prices over the
   window (today → today + N months).
3. `report.build_report` turns the flat list of nights into per-month
   calendar grids; every cell gets a `href` to Hyatt's award search.
4. `report.render_html` renders all hotels into one HTML file via Jinja2.

Fetchers implement a small `Fetcher` Protocol:

- **`MockFetcher`** — deterministic synthetic pricing derived from
  `AWARD_CHART`. No network. Used by default and as a CI fallback.
- **`PlaywrightFetcher`** — launches headless Chromium, navigates Hyatt's
  award booking page for each hotel/window, **intercepts JSON network
  responses** rather than calling any API directly, and walks the captured
  JSON for `(date, points)` pairs (`_walk_for_date_points`). When it
  cannot find a code for a hotel it tries `_discover_code` via Hyatt's
  search. On any failure it returns blanks instead of raising.
- **`CachingFetcher`** — wraps another fetcher with an on-disk JSON cache
  keyed by `(hotel_slug, start, end)`. Always wrapped around the live
  fetcher to avoid re-hitting Hyatt.

The "live" path is intentionally best-effort:
- Hyatt uses Akamai bot detection; datacenter IPs (including GH Actions
  runners) may be blocked.
- The JSON shape changes periodically; the parser is heuristic.
- Failures degrade gracefully: cells render as `?` but the deeplinks
  remain tappable, so the bookmarked page is still useful.

## Conventions

- **Code style:** Standard Python; `from __future__ import annotations` at
  the top of every module. Prefer `dataclass(frozen=True)` for value types.
- **Type hints:** Required on all function signatures.
- **Module shape:** Keep modules small and single-purpose. Don't merge
  `client.py` and `report.py`.
- **Logging:** Use `logging.getLogger(__name__)` per module; CLI wires the
  root logger. Don't use `print`.
- **Secrets:** None currently. If anything in the live flow ever needs auth,
  load from env vars; never commit cookies or session tokens.
- **External requests:** Be polite. `PlaywrightFetcher` defaults to 4s
  throttle between 30-night chunks and one hotel at a time. Always go
  through `CachingFetcher` for live runs. Don't add concurrency without
  thinking about Akamai's response.
- **Live failures are not exceptions.** A blocked fetch should produce
  `NightPrice(..., points=None, tier=None)` so the report still renders;
  log a warning and move on.

## Branching & Commits

- Default branch: `main` (once it exists on the remote).
- AI session branches: `claude/<slug>`. User branches: `<user>/<slug>`.
- Open a PR against `main`; don't push directly.
- One logical change per commit. Commit message explains the "why".

## Things AI Assistants Should Know

- This is a personal project. Favor small, readable code over heavy abstraction.
- The user is phone-only and not a developer. Choose architectures that work
  without a laptop: cloud cron + GH Pages + deeplinks over CLI-only tools.
- Don't add features the task didn't ask for. No new frameworks or
  dependencies without checking with the maintainer.
- Default to `--source mock` while iterating; only use `--source live` when
  you actually want to hit hyatt.com.
- `data/hotels.json` is hand-maintained and almost certainly incomplete.
  Hyatt re-shuffles categories twice a year — verify entries against
  Hyatt's current category list before trusting the output.
- Property `code` fields can be `null`; the live fetcher will try to
  discover them and the deeplinks fall back to name-based searches.
- Don't commit credentials, session cookies, or personal reservation data.
- Update this file when structure, stack, or workflow changes meaningfully.

## Open Questions

- [ ] Whether GH Actions runner IPs reliably pass Hyatt's Akamai check.
      If not, consider self-hosted runners on a residential connection, or
      switching to fully manual flow (deeplink-only report).
- [ ] Fill in real 5-letter property `code` values in `data/hotels.json`
      to skip the per-hotel discovery step (saves time and is more robust).
- [ ] Add "diff vs. last run" so the report highlights nights whose price
      changed since the previous successful fetch.
- [ ] Consider trimming the hotel list to a user-chosen favorites set,
      since 28 × 180 nights is more than anyone actually wants to scan.
