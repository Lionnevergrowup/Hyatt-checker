# Hyatt-checker

Generates a 6-month award-pricing report for Category 1 & 2 World of Hyatt
properties in the United States. Output is a single mobile-friendly HTML page:
one section per hotel, each with month-by-month calendars showing the points
cost for every night, color-coded off-peak / standard / peak.

**Every date cell is also a tappable link** to Hyatt's award search for that
night, so when a cell shows `?` (live fetch failed for that night) you can
verify it with one tap on your phone.

## How it's meant to be used (phone-only setup)

1. Enable GitHub Pages on this repo:
   **Settings → Pages → Source: "GitHub Actions"**.
2. Open the **Actions** tab → "Weekly Hyatt report" → **Run workflow**
   (the button is also in the GitHub mobile app).
3. After it finishes (~10–20 min), open
   `https://<your-user>.github.io/Hyatt-checker/` and bookmark it on your
   phone home screen.
4. The workflow re-runs automatically every Sunday. Tap "Run workflow" any
   time you want a fresh report sooner.

If the live fetch is blocked by Hyatt's anti-bot (it happens — Akamai is
aggressive), the workflow falls back to publishing a synthetic-data report so
the bookmarked page never breaks. The deeplinks always work either way.

## Quick start (local)

```bash
# install (mock-only — no browser)
pip install -e .

# generate a report with synthetic data (no network calls)
hyatt-checker --source mock --output output/report.html
open output/report.html
```

To run the live fetcher locally:

```bash
pip install -e ".[live]"
playwright install chromium
hyatt-checker --source live --output output/report.html -v
```

## CLI

```
hyatt-checker [--hotels data/hotels.json]
              [--output output/report.html]
              [--months 6]
              [--source mock|live]
              [--no-cache] [--cache-dir .cache]
              [-v]
```

- `--source mock` — synthetic pricing from Hyatt's published award chart. No
  network calls. Use for development and as a structural sanity check.
- `--source live` — drives a headless Chromium via Playwright through Hyatt's
  award search and intercepts the JSON responses it loads. Best-effort: if
  Hyatt blocks the request, that hotel's nights come back as `?` (still
  tappable to verify manually).

## How the live fetcher works

Hyatt has no public API and their internal endpoints are protected by
Akamai bot detection. Rather than guess the API contract and fake browser
fingerprints, `PlaywrightFetcher` opens the real booking page in a real
browser, lets Hyatt's own JavaScript issue the pricing requests, and listens
for the JSON responses. The parser then walks the JSON tree for any
`(date, points)` pairs.

This is fragile by nature:

- Datacenter IPs (including GitHub Actions runners) are more likely to be
  blocked than residential ones.
- Hyatt restructures responses periodically; the heuristic parser tolerates
  renames but a structural overhaul will break it.

When it fails, the report still renders — points become `?`, calendar cells
remain tappable. That keeps the bookmark useful even on a bad day.

## Hotel list

`data/hotels.json` is a hand-maintained list of US Cat 1 & 2 properties.
Hyatt re-shuffles categories twice a year, so verify against the current
Hyatt category list before relying on the output.

Each entry:

```json
{"code": null, "name": "Hyatt Place ...", "category": 2, "city": "...", "state": "..", "country": "US"}
```

`code` is the 5-letter Hyatt property code. It's optional — when missing,
`PlaywrightFetcher` discovers it by searching the hotel name on hyatt.com
on first run, and deeplinks fall back to a name-based search.

## Output

A single self-contained HTML file. Each hotel section shows 6+ month grids;
cells display points required, colored by tier:

- green = off-peak
- yellow = standard
- red = peak
- gray (`?`) = unknown / fetch failed / sold out — tap to verify on hyatt.com

## Layout

```
.
├── .github/workflows/weekly.yml  # scheduled + manual GH Actions job → GH Pages
├── data/hotels.json              # curated Cat 1 & 2 US list
├── src/hyatt_checker/
│   ├── cli.py                    # argparse entry point
│   ├── client.py                 # Fetcher protocol + Mock / Playwright / Caching
│   ├── hotels.py                 # Hotel dataclass + JSON loader
│   └── report.py                 # HTML calendar rendering (Jinja2) + deeplinks
├── pyproject.toml
└── README.md
```
