from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment

from hyatt_checker.client import NightPrice
from hyatt_checker.hotels import Hotel


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


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hyatt Cat 1 & 2 US — Award Pricing</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.4 -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; padding: 0 1rem; }
  h1 { margin: 0 0 0.25rem; }
  .meta { color: #666; margin-bottom: 2rem; }
  .hotel { border-top: 2px solid #ddd; padding: 1.5rem 0; }
  .hotel h2 { margin: 0 0 0.25rem; }
  .hotel .sub { color: #666; margin-bottom: 1rem; font-size: 13px; }
  .months { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }
  .month h3 { margin: 0 0 0.5rem; font-size: 14px; font-weight: 600; }
  table.cal { border-collapse: collapse; width: 100%; table-layout: fixed; }
  table.cal th, table.cal td { border: 1px solid #e2e2e2; padding: 4px 2px; text-align: center; vertical-align: top; height: 48px; font-size: 11px; }
  table.cal th { background: #f5f5f5; font-weight: 600; font-size: 11px; }
  td .day { color: #999; font-size: 10px; display: block; }
  td .pts { font-weight: 600; font-size: 12px; }
  td.off-peak { background: #e6f4ea; }
  td.standard { background: #fff8e1; }
  td.peak     { background: #fdecea; }
  td.unavail  { background: #f5f5f5; color: #bbb; }
  td.empty    { background: transparent; border-color: transparent; }
  .legend { margin: 0.5rem 0 1.5rem; font-size: 12px; }
  .legend span { display: inline-block; padding: 2px 8px; margin-right: 6px; border-radius: 3px; }
</style>
</head>
<body>
  <h1>Hyatt Cat 1 & 2 — US Award Pricing</h1>
  <p class="meta">Generated {{ generated_at }} · {{ window_start }} → {{ window_end }} · {{ reports|length }} properties</p>
  <p class="legend">
    <span class="off-peak">off-peak</span>
    <span class="standard">standard</span>
    <span class="peak">peak</span>
    <span class="unavail">unavailable</span>
  </p>
  {% for r in reports %}
  <section class="hotel">
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
                {% elif cell.points is none and cell.tier is none and cell.day == 0 %}
                  <td class="empty"></td>
                {% else %}
                  <td class="{{ cell.tier or 'unavail' }}">
                    <span class="day">{{ cell.day }}</span>
                    <span class="pts">{{ '{:,}'.format(cell.points) if cell.points else '—' }}</span>
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
        months.append(_build_month(cur.year, cur.month, by_day, start, end))
        # advance to first of next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return HotelReport(hotel=hotel, months=months)


def _build_month(
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
            if price is None:
                row.append(Cell(day=day, points=None, tier=None))
            else:
                row.append(Cell(day=day, points=price.points, tier=price.tier))
        weeks.append(row)
    return MonthGrid(year=year, month=month, weeks=weeks)


def render_html(reports: list[HotelReport], start: date, end: date, generated_at: str) -> str:
    env = Environment(autoescape=True)
    tmpl = env.from_string(TEMPLATE)
    return tmpl.render(
        reports=reports,
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        generated_at=generated_at,
    )


def write_report(html: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
