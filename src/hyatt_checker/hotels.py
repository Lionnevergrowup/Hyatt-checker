from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Hotel:
    code: str | None
    name: str
    category: int
    city: str
    state: str
    country: str = "US"
    property_url: str | None = None  # canonical hyatt.com URL for the deeplink

    @property
    def slug(self) -> str:
        return (self.code or self.name).lower().replace(" ", "-").replace("/", "-")


def load_hotels(path: Path) -> list[Hotel]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Hotel(**entry) for entry in raw]


def filter_us_cat_1_2(hotels: list[Hotel]) -> list[Hotel]:
    return [h for h in hotels if h.country == "US" and h.category in (1, 2)]
