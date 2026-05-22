from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment

from hyatt_checker.client import AWARD_CHART, NightPrice
from hyatt_checker.hotels import Hotel


def hyatt_deeplink(hotel: Hotel, night: date) -> str:
    """URL that opens this hotel's Hyatt page for the given night.

    Each hotel in data/hotels.json carries a verified property_url
    (the canonical hyatt.com URL we resolved by Google-searching). We
    append checkinDate/checkoutDate query params — if Hyatt parses them
    the booking widget pre-fills, otherwise the user lands on the
    property page and picks dates manually. On a phone with the Hyatt
    app installed, universal links route the URL into the app where
    the user's existing session bypasses Kasada bot detection.

    Falls back to a Google search when no property_url is set (e.g.,
    for hand-added hotels that haven't been resolved yet).
    """
    checkin = night.isoformat()
    checkout = (night + timedelta(days=1)).isoformat()
    if hotel.property_url:
        sep = "&" if "?" in hotel.property_url else "?"
        return (
            f"{hotel.property_url}{sep}"
            f"checkinDate={checkin}&checkoutDate={checkout}"
            f"&rooms=1&adults=1&rate=woh"
        )
    if hotel.code:
        return (
            f"https://www.hyatt.com/shop/rooms/{hotel.code}"
            f"?checkinDate={checkin}&checkoutDate={checkout}"
            f"&rooms=1&adults=1&rate=woh"
        )
    from urllib.parse import quote
    query = f"{hotel.name} hyatt {night.strftime('%B %d %Y')} book"
    return f"https://www.google.com/search?q={quote(query)}&btnI=I"


@dataclass
class HotelReport:
    hotel: Hotel
    months: list["MonthGrid"]
    summary: "HotelSummary"


@dataclass
class HotelSummary:
    nights_known: int
    nights_unknown: int
    cheapest_points: int | None
    nights_changed: int
    chart_range: str  # e.g. "3,000–9,000"


@dataclass
class MonthGrid:
    year: int
    month: int
    weeks: list[list["Cell | None"]]  # 6 rows x 7 cols, None for padding

    @property
    def label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"


@dataclass
class Cell:
    day: int
    points: int | None
    tier: str | None
    href: str
    delta: int | None = None  # change vs previous run (+ = went up, − = down)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hyatt Cat 1 & 2 US — Award Pricing</title>
<style>
  :root { color-scheme: light dark; --border: #e2e2e2; --muted: #666; --bg: #fff; --fg: #111; --accent: #1a73e8; }
  body { font: 15px/1.4 -apple-system, system-ui, sans-serif; margin: 0 auto; max-width: 1100px; padding: 0.75rem; background: var(--bg); color: var(--fg); }
  h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
  .meta { color: var(--muted); margin: 0 0 0.5rem; font-size: 13px; }
  .legend { margin: 0.25rem 0 0.5rem; font-size: 12px; }
  .legend span { display: inline-block; padding: 2px 8px; margin-right: 4px; border-radius: 3px; }
  .help { color: var(--muted); font-size: 12px; margin: 0 0 0.75rem; }
  nav.index { background: #f8f8f8; border: 1px solid var(--border); border-radius: 6px; padding: 0.5rem 0.75rem; margin: 0.5rem 0 1.25rem; font-size: 13px; }
  nav.index h2 { font-size: 13px; margin: 0 0 0.4rem; font-weight: 600; color: var(--muted); }
  nav.index ul { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.15rem 0.75rem; }
  nav.index a { color: var(--accent); text-decoration: none; }
  nav.index .cat { color: var(--muted); font-size: 11px; }
  nav.index .min { color: #1f7a3a; font-weight: 600; font-size: 11px; margin-left: 0.25rem; }
  details.hotel { border-top: 2px solid #ddd; padding: 0.75rem 0; }
  details.hotel[open] { padding-bottom: 1.25rem; }
  details.hotel > summary { cursor: pointer; list-style: none; padding: 0.25rem 0; }
  details.hotel > summary::-webkit-details-marker { display: none; }
  details.hotel > summary h2 { display: inline; font-size: 1.1rem; margin: 0; }
  details.hotel > summary .sub { color: var(--muted); font-size: 12px; margin-left: 0.5rem; }
  details.hotel > summary .badge { display: inline-block; background: #eef; color: #336; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 0.4rem; vertical-align: 1px; }
  details.hotel > summary .badge.changed { background: #fff0c2; color: #6a4a00; }
  .months { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 0.75rem; }
  .month h3 { margin: 0 0 0.4rem; font-size: 13px; font-weight: 600; }
  table.cal { border-collapse: collapse; width: 100%; table-layout: fixed; }
  table.cal th, table.cal td { border: 1px solid var(--border); padding: 0; text-align: center; vertical-align: top; height: 50px; font-size: 11px; position: relative; }
  table.cal th { background: #f5f5f5; font-weight: 600; font-size: 10px; padding: 4px 0; }
  td a { display: block; height: 100%; padding: 4px 2px; color: inherit; text-decoration: none; }
  td a:active { opacity: 0.6; }
  td .day { color: #888; font-size: 10px; display: block; }
  td .pts { font-weight: 600; font-size: 12px; }
  td .delta { position: absolute; top: 1px; right: 3px; font-size: 9px; font-weight: 700; }
  td .delta.up { color: #c0392b; }
  td .delta.down { color: #196f3d; }
  td.lowest   { background: #c8e6c9; }
  td.low      { background: #e6f4ea; }
  td.moderate { background: #fff8e1; }
  td.upper    { background: #ffe0b2; }
  td.top      { background: #fdecea; }
  td.unknown  { background: #fafafa; color: #aaa; }
  td.empty    { background: transparent; border-color: transparent; }
  .back-to-top { display: block; text-align: right; font-size: 12px; color: var(--accent); text-decoration: none; margin-top: 0.5rem; }
  .help button { font-size: 12px; padding: 2px 8px; margin-left: 0.4rem; border: 1px solid var(--border); background: transparent; color: var(--accent); border-radius: 4px; cursor: pointer; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #111; --fg: #eee; --border: #2a2a2a; --muted: #aaa; --accent: #66aaff; }
    nav.index { background: #181818; }
    nav.index .min { color: #5acc7a; }
    details.hotel { border-color: #333; }
    table.cal th { background: #1a1a1a; }
    td.lowest   { background: #0e5a23; }
    td.low      { background: #163e21; }
    td.moderate { background: #4a3a00; }
    td.upper    { background: #5a3500; }
    td.top      { background: #4a1d1d; }
    td.unknown  { background: #1a1a1a; }
    details.hotel > summary .badge { background: #223; color: #cce; }
    details.hotel > summary .badge.changed { background: #5a4400; color: #ffe27a; }
  }
</style>
</head>
<body>
  <h1 id="top">Hyatt Cat 1 & 2 — US Award Pricing</h1>
  <p class="meta">Updated {{ generated_at }} · {{ window_start }} → {{ window_end }} · {{ reports|length }} hotels · source: {{ source }}</p>
  <p class="legend">
    <span class="lowest">lowest</span>
    <span class="low">low</span>
    <span class="moderate">moderate</span>
    <span class="upper">upper</span>
    <span class="top">top</span>
    <span class="unknown">? = tap to check</span>
  </p>
  <p class="help">Tap any date to open Hyatt's award search for that night. Tap a hotel name to expand/collapse. Hyatt blocks automated price lookups (Kasada bot detection), so cells show "?" — your phone's normal session passes through.
    <button type="button" id="expandAll">expand all</button>
    <button type="button" id="collapseAll">collapse all</button>
  </p>

  <nav class="index">
    <h2>Hotels ({{ reports|length }})</h2>
    <ul>
      {% for r in reports %}
      <li>
        <a href="#{{ r.hotel.slug }}">{{ r.hotel.name }}</a>
        <span class="cat">cat {{ r.hotel.category }} · {{ r.summary.chart_range }}</span>
        {% if r.summary.cheapest_points %}
        <span class="min">from {{ '{:,}'.format(r.summary.cheapest_points) }}</span>
        {% endif %}
      </li>
      {% endfor %}
    </ul>
  </nav>

  {% for r in reports %}
  <details class="hotel" id="{{ r.hotel.slug }}">
    <summary>
      <h2>{{ r.hotel.name }}</h2>
      <span class="sub">Cat {{ r.hotel.category }} · {{ r.hotel.city }}, {{ r.hotel.state }} · {{ r.summary.chart_range }} pts{% if r.hotel.code %} · {{ r.hotel.code }}{% endif %}</span>
      {% if r.summary.cheapest_points %}
      <span class="badge">from {{ '{:,}'.format(r.summary.cheapest_points) }} pts</span>
      {% endif %}
      {% if r.summary.nights_changed %}
      <span class="badge changed">{{ r.summary.nights_changed }} changed</span>
      {% endif %}
    </summary>
    <div class="months">
      {% for m in r.months %}
      <div class="month">
        <h3>{{ m.label }}</h3>
        <table class="cal">
          <thead><tr><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th><th>Sun</th></tr></thead>
          <tbody>
          {% for week in m.weeks %}
            <tr>
              {% for cell in week %}
                {% if cell is none %}
                  <td class="empty"></td>
                {% else %}
                  <td class="{{ cell.tier or 'unknown' }}">
                    <a href="{{ cell.href }}" target="_blank" rel="noopener">
                      <span class="day">{{ cell.day }}</span>
                      <span class="pts">{% if cell.points %}{{ '{:,}'.format(cell.points) }}{% else %}?{% endif %}</span>
                      {% if cell.delta %}
                        <span class="delta {{ 'up' if cell.delta > 0 else 'down' }}">{{ '▲' if cell.delta > 0 else '▼' }}</span>
                      {% endif %}
                    </a>
                  </td>
                {% endif %}
              {% endfor %}
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
      {% endfor %}
    </div>
    <a class="back-to-top" href="#top">↑ back to top</a>
  </details>
  {% endfor %}
  <script>
    // Make anchor links (and the index) actually open the collapsed section.
    function openTargetFromHash() {
      if (!location.hash) return;
      var el = document.querySelector(location.hash);
      if (el && el.tagName === 'DETAILS') el.open = true;
    }
    window.addEventListener('hashchange', openTargetFromHash);
    openTargetFromHash();
    document.getElementById('expandAll').addEventListener('click', function () {
      document.querySelectorAll('details.hotel').forEach(function (d) { d.open = true; });
    });
    document.getElementById('collapseAll').addEventListener('click', function () {
      document.querySelectorAll('details.hotel').forEach(function (d) { d.open = false; });
    });
  </script>
</body>
</html>
"""


def build_report(
    hotel: Hotel,
    prices: list[NightPrice],
    start: date,
    end: date,
    previous: dict[str, int] | None = None,
) -> HotelReport:
    by_day: dict[date, NightPrice] = {p.night: p for p in prices}
    prev = previous or {}
    months: list[MonthGrid] = []
    seen: set[tuple[int, int]] = set()
    cur = date(start.year, start.month, 1)
    while cur < end:
        key = (cur.year, cur.month)
        if key in seen:
            break
        seen.add(key)
        months.append(_build_month(hotel, cur.year, cur.month, by_day, prev, start, end))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return HotelReport(hotel=hotel, months=months, summary=_summarize(hotel, months))


def _summarize(hotel: Hotel, months: list[MonthGrid]) -> HotelSummary:
    known = 0
    unknown = 0
    cheapest: int | None = None
    changed = 0
    for m in months:
        for week in m.weeks:
            for cell in week:
                if cell is None:
                    continue
                if cell.points:
                    known += 1
                    if cheapest is None or cell.points < cheapest:
                        cheapest = cell.points
                else:
                    unknown += 1
                if cell.delta:
                    changed += 1
    chart = AWARD_CHART.get(hotel.category)
    chart_range = (
        f"{chart[0]:,}–{chart[-1]:,}" if chart else "?"
    )
    return HotelSummary(
        nights_known=known,
        nights_unknown=unknown,
        cheapest_points=cheapest,
        nights_changed=changed,
        chart_range=chart_range,
    )


def _build_month(
    hotel: Hotel,
    year: int,
    month: int,
    by_day: dict[date, NightPrice],
    previous: dict[str, int],
    window_start: date,
    window_end: date,
) -> MonthGrid:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks: list[list[Cell | None]] = []
    for week in cal.monthdayscalendar(year, month):
        row: list[Cell | None] = []
        for day in week:
            if day == 0:
                row.append(None)
                continue
            d = date(year, month, day)
            if d < window_start or d >= window_end:
                row.append(None)
                continue
            price = by_day.get(d)
            points = price.points if price else None
            tier = price.tier if price else None
            prev_points = previous.get(d.isoformat())
            delta = (points - prev_points) if (points and prev_points and points != prev_points) else None
            row.append(
                Cell(
                    day=day,
                    points=points,
                    tier=tier,
                    href=hyatt_deeplink(hotel, d),
                    delta=delta,
                )
            )
        weeks.append(row)
    return MonthGrid(year=year, month=month, weeks=weeks)


def render_html(
    reports: list[HotelReport],
    start: date,
    end: date,
    generated_at: str,
    source: str = "mock",
) -> str:
    env = Environment(autoescape=True)
    tmpl = env.from_string(TEMPLATE)
    return tmpl.render(
        reports=reports,
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        generated_at=generated_at,
        source=source,
    )


def write_report(html: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
