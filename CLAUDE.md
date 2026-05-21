# CLAUDE.md

Guidance for AI assistants (Claude Code and similar tools) working in this repository.

## Project Overview

**Name:** Hyatt-checker

**Purpose:** Generate a 6-month award-pricing report for Category 1 & 2 World of
Hyatt hotels in the United States. Output is a single HTML file with one
section per hotel, each containing a month-by-month calendar showing the points
cost for every night (color-coded off-peak / standard / peak / unavailable).

**Primary use case:** CLI tool run on demand (or on a schedule) to produce a
static HTML report for a single user to browse.

## Repository Structure

```
.
├── data/
│   └── hotels.json              # Curated list of US Cat 1 & 2 properties
├── src/hyatt_checker/
│   ├── __init__.py
│   ├── __main__.py              # `python -m hyatt_checker` entry
│   ├── cli.py                   # argparse entry point (hyatt-checker command)
│   ├── hotels.py                # Hotel dataclass + JSON loader / filter
│   ├── client.py                # Fetcher protocol + Mock/Live/Caching impls + award chart
│   └── report.py                # Jinja2 HTML calendar rendering
├── output/                      # Generated HTML reports (gitignored)
├── .cache/                      # On-disk pricing cache (gitignored)
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

## Tech Stack

- **Language & runtime:** Python 3.11+
- **Package manager:** `pip` (project uses `pyproject.toml` with hatchling)
- **Key libraries:**
  - `httpx` — HTTP client (used by `LiveFetcher`)
  - `jinja2` — HTML templating
- **Storage:** JSON files (hotel list + cached pricing). No database.
- **Hosting:** Run locally or in CI (e.g., GitHub Actions on a schedule).

## Development Workflow

```bash
# install (editable)
pip install -e .

# generate report with synthetic data — no network calls, safe to run anytime
hyatt-checker --source mock --output output/report.html

# verbose
hyatt-checker --source mock -v
```

There are no tests yet. There is no linter/formatter configured yet. Add `ruff`
when the codebase grows.

## Architecture

The pipeline is small and linear:

1. `cli.main` loads `data/hotels.json` and filters to `country=US` and
   `category in {1, 2}`.
2. For each hotel it asks a `Fetcher` for nightly point prices over the
   window (today → today + N months).
3. `report.build_report` turns the flat list of nights into a list of
   `MonthGrid`s (calendar weeks).
4. `report.render_html` renders all hotels into one HTML file via Jinja2.

The `Fetcher` protocol has three implementations:

- **`MockFetcher`** — deterministic synthetic pricing derived from the
  official Hyatt award chart (`AWARD_CHART` in `client.py`). Used by default.
  No network calls.
- **`LiveFetcher`** — skeleton only. Hyatt has no public API; the real
  endpoint needs to be captured from browser devtools and wired into
  `_fetch_one`. See the module docstring in `client.py`.
- **`CachingFetcher`** — wraps another fetcher with an on-disk JSON cache
  keyed by `(hotel_slug, start, end)`. Always use this around `LiveFetcher`.

## Conventions

- **Code style:** Standard Python; `from __future__ import annotations` at the
  top of every module. Prefer `dataclass(frozen=True)` for value types.
- **Type hints:** Required on all function signatures.
- **Module shape:** Keep modules small and single-purpose. Don't merge
  `client.py` and `report.py`.
- **Logging:** Use `logging.getLogger(__name__)` per module; CLI wires the
  root logger. Don't use `print`.
- **Secrets:** None at the moment. If `LiveFetcher` ever needs auth, load
  from env vars; never commit cookies or session tokens.
- **External APIs:** Be conservative with hyatt.com requests. Default
  throttle in `LiveFetcher` is 2s between chunks of 30 nights. Always go
  through `CachingFetcher` for live runs.

## Branching & Commits

- Default branch: `main` (once it exists on the remote).
- Feature work on `claude/<slug>` (AI sessions) or `<user>/<slug>`.
- Open a PR against `main`; don't push directly.
- One logical change per commit. Commit message explains the "why".

## Things AI Assistants Should Know

- This is a personal project. Favor small, readable code over heavy abstraction.
- Don't add features the task didn't ask for. No frameworks or dependencies
  without checking with the maintainer.
- When making web requests against Hyatt or other live services, be conservative
  during development. Prefer `--source mock` while iterating.
- The `data/hotels.json` list is hand-maintained and almost certainly incomplete.
  Hyatt re-shuffles categories twice a year — verify entries against Hyatt's
  current category list before relying on the output.
- Property `code` fields are currently `null`. They're only needed for
  `--source live` and must be the real 5-letter Hyatt property codes.
- Don't commit credentials, session cookies, or personal reservation data.
- Update this file when structure, stack, or workflow changes meaningfully.

## Open Questions

- [ ] Capture Hyatt's real pricing endpoint and implement `LiveFetcher._fetch_one`.
- [ ] Fill in real property `code` values in `data/hotels.json`.
- [ ] Decide where this runs on a schedule (GitHub Actions? local cron?) and how
      the generated HTML is delivered (commit to gh-pages? email? S3?).
- [ ] Decide whether to add "diff vs. last run" so the user only sees nights
      that changed.
