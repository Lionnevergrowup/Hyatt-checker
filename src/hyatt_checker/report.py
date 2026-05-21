from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment

from hyatt_checker.client import NightPrice
from hyatt_checker.hotels import Hotel


def hyatt_deeplink(hotel: Hotel, night: date) -> str:
    """URL that opens Hyatt's award search for one night at this hotel.

    On a phone this opens the Hyatt app if installed, otherwise the
    mobile site. Works whether the property `code` is filled in or not —
    falls back to a name-based search.
    """
    checkin = night.isoformat()
    checkout = (night + timedelta(days=1)).isoformat()
    if hotel.code:
        return (
            f"https://www.hyatt.com/shop/rooms/{hotel.code}"
            f"?checkinDate={checkin}&checkoutDate={checkout}"
            f"&rooms=1&adults=1&rate=woh"
        )
    from urllib.parse import quote
    return (
        f"https://www.hyatt.com/search/hotels?q={quote(hotel.name)}"
        f"&checkinDate={checkin}&checkoutDate={checkout}&rate=woh"
    )


@dataclass
class HotelReport:
    hotel: Hotel
    months: list["MonthGrid"]


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


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hyatt Cat 1 & 2 US — Award Pricing</title>
<style>
  :root { color-scheme: light dark; --border: #e2e2e2; --muted: #666; }
  body { font: 15px/1.4 -apple-system, system-ui, sans-serif; margin: 1rem auto; max-width: 1100px; padding: 0 0.75rem; }
  h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
  .meta { color: var(--muted); margin: 0 0 0.5rem; font-size: 13px; }
  .hotel { border-top: 2px solid #ddd; padding: 1.25rem 0; }
  .hotel h2 { margin: 0 0 0.25rem; font-size: 1.1rem; }
  .hotel .sub { color: var(--muted); margin-bottom: 0.75rem; font-size: 13px; }
  .months { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
  .month h3 { margin: 0 0 0.4rem; font-size: 13px; font-weight: 600; }
  table.cal { border-collapse: collapse; width: 100%; table-layout: fixed; }
  table.cal th, table.cal td { border: 1px solid var(--border); padding: 0; text-align: center; vertical-align: top; height: 46px; font-size: 11px; }
  table.cal th { background: #f5f5f5; font-weight: 600; font-size: 10px; padding: 4px 0; }
  td a { display: block; height: 100%; padding: 4px 2px; color: inherit; text-decoration: none; }
  td a:active { opacity: 0.6; }
  td .day { color: #888; font-size: 10px; display: block; }
  td .pts { font-weight: 600; font-size: 12px; }
  td.off-peak { background: #e6f4ea; }
  td.standard { background: #fff8e1; }
  td.peak     { background: #fdecea; }
  td.unknown  { background: #fafafa; color: #aaa; }
  td.empty    { background: transparent; border-color: transparent; }
  .legend { margin: 0.25rem 0 1rem; font-size: 12px; }
  .legend span { display: inline-block; padding: 2px 8px; margin-right: 4px; border-radius: 3px; }
  .help { color: var(--muted); font-size: 12px; margin: 0 0 1rem; }
  @media (prefers-color-scheme: dark) {
    body { background: #111; color: #eee; }
    .hotel { border-color: #333; }
    table.cal th, table.cal td { border-color: #2a2a2a; }
    table.cal th { background: #1a1a1a; }
    td.off-peak { background: #163e21; }
    td.standard { background: #4a3a00; }
    td.peak     { background: #4a1d1d; }
    td.unknown  { background: #1a1a1a; }
  }
</style>
</head>
<body>
  <h1>Hyatt Cat 1 & 2 — US Award Pricing</h1>
  <p class="meta">Updated {{ generated_at }} · {{ window_start }} → {{ window_end }} · {{ reports|length }} hotels · source: {{ source }}</p>
  <p class="legend">
    <span class="off-peak">off-peak</span>
    <span class="standard">standard</span>
    <span class="peak">peak</span>
    <span class="unknown">? = tap to check</span>
  </p>
  <p class="help">Tap any date to open Hyatt's award search for that night.</p>
  {% for r in reports %}
  <section class="hotel" id="{{ r.hotel.slug }}">
    <h2>{{ r.hotel.name }}</h2>
    <p class="sub">Category {{ r.hotel.category }} · {{ r.hotel.city }}, {{ r.hotel.state }}{% if r.hotel.code %} · {{ r.hotel.code }}{% endif %}</p>
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
  </section>
  {% endfor %}
</body>
</html>
"""


def build_report(
    hotel: Hotel, prices: list[NightPrice], start: date, end: date
) -> HotelReport:
    by_day: dict[date, NightPrice] = {p.night: p for p in prices}
    months: list[MonthGrid] = []
    seen: set[tuple[int, int]] = set()
    cur = date(start.year, start.month, 1)
    while cur < end:
        key = (cur.year, cur.month)
        if key in seen:
            break
        seen.add(key)
        months.append(_build_month(hotel, cur.year, cur.month, by_day, start, end))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return HotelReport(hotel=hotel, months=months)


def _build_month(
    hotel: Hotel,
    year: int,
    month: int,
    by_day: dict[date, NightPrice],
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
            row.append(
                Cell(
                    day=day,
                    points=price.points if price else None,
                    tier=price.tier if price else None,
                    href=hyatt_deeplink(hotel, d),
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
