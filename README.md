# Hyatt-checker

Generates a 6-month award-pricing report for Category 1 & 2 World of Hyatt
properties in the United States. Output is a single HTML file: one section per
hotel, each with a month-by-month calendar showing the points cost for every
night (color-coded off-peak / standard / peak).

## Quick start

```bash
# install (editable)
pip install -e .

# generate a report with synthetic data (no network calls)
hyatt-checker --source mock --output output/report.html

# open the result
open output/report.html
```

The default `--source mock` uses Hyatt's published award chart to generate
plausible synthetic pricing. This is what you want for development and for
verifying the report layout. **No requests are made to hyatt.com.**

## CLI

```
hyatt-checker [--hotels data/hotels.json]
              [--output output/report.html]
              [--months 6]
              [--source mock|live]
              [--no-cache] [--cache-dir .cache]
              [-v]
```

## Hotel list

`data/hotels.json` is a hand-maintained list of US Cat 1 & 2 properties.
Hyatt re-shuffles categories twice a year, so verify against the current
[Hyatt category list](https://world.hyatt.com/content/gp/en/rates/category-changes.html)
before relying on the output.

Each entry:

```json
{"code": "iadzh", "name": "...", "category": 2, "city": "...", "state": "DC", "country": "US"}
```

`code` is the 5-letter Hyatt property code used by their booking system. It
can be `null` when running with `--source mock`; it's required for `--source live`.

## Live data

`--source live` is not yet wired up. Hyatt has no public pricing API, so the
real fetcher has to call their internal booking endpoint, which requires
session cookies / anti-bot tokens and changes periodically. The skeleton is
in `src/hyatt_checker/client.py` (`LiveFetcher`) with notes on what to fill in:

1. Open Hyatt's award search in a browser with devtools.
2. Capture the JSON request that returns nightly point pricing.
3. Implement `LiveFetcher._fetch_one` against that endpoint.
4. Keep the throttle conservative — the default is 2s between chunks of 30
   nights. Always run through `CachingFetcher` so reruns don't re-hit Hyatt.

Be a polite client. Don't hammer hyatt.com during development.

## Output

A single self-contained HTML file. Each hotel section shows up to 6 month
grids; cells display points required, colored by tier:

- green = off-peak
- yellow = standard
- red = peak
- gray = unavailable on points

## Layout

```
.
├── data/hotels.json           # curated Cat 1 & 2 US list
├── src/hyatt_checker/
│   ├── cli.py                 # argparse entry point
│   ├── client.py              # Fetcher protocol + Mock/Live/Caching
│   ├── hotels.py              # Hotel dataclass + JSON loader
│   └── report.py              # HTML calendar rendering (Jinja2)
├── pyproject.toml
└── README.md
```
