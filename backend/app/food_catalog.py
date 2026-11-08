"""The Food Nearby catalog: loading the authoritative JSON, seeding it, and reading ratings.

``data/food_catalog.json`` is the single source of truth for venues and their station names.
(The frontend still ships an identical copy until it reads the API; a frontend test fails if
the two ever differ.) Seeding is repeatable: records are matched by stable IDs, changed fields
are updated, records that left the catalog are deactivated, and nothing is ever deleted or
invented. Menu items and appearances are never seeded.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .food_models import (
    FoodMenuItem, FoodReview, FoodStation, FoodVenue, FoodVenueRating, ModerationState, ReviewTarget, VenueKind, VenueOperator,
    WalletAcceptance,
)
from .models import _now

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "food_catalog.json"


@lru_cache(maxsize=4)
def load_catalog(path: Path = CATALOG_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower().replace("'", "").replace("’", "")).strip("-")


def station_id(venue_id: str, station_name: str) -> str:
    """Deterministic station ID, e.g. ("pines", "Slice at Pines") -> "pines--slice-at-pines"."""
    return f"{venue_id}--{_slug(station_name)}"


def menu_name_key(name: str) -> str:
    """The identity rule for dishes at one station: case- and spacing-insensitive name.

    "Chicken  Rice Bowl" and "chicken rice bowl" are the same item; anything else is a new item.
    Merging differently worded dishes is a curation decision, never automatic.
    """
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def _venue_fields(venue: dict, catalog: dict) -> dict:
    coordinates = venue["coordinates"]
    links = venue["links"]
    wallets = venue["wallets"]
    return {
        "name": venue["name"],
        "operator": VenueOperator(venue["operator"]),
        "kind": VenueKind(venue["kind"]),
        "summary": venue["summary"],
        "description": venue["description"],
        "tags": list(venue["tags"]),
        "campus_area": venue["campusArea"],
        "location": venue["location"],
        "on_campus": bool(venue["onCampus"]),
        "latitude": coordinates["lat"] if coordinates else None,
        "longitude": coordinates["lng"] if coordinates else None,
        "coordinates_source": (
            {"layer": coordinates["layer"], "feature": coordinates["feature"], "building": coordinates["building"]}
            if coordinates else None
        ),
        "hours": venue["hours"],
        "menu_url": links.get("menu"),
        "website_url": links.get("website"),
        "dining_dollars_acceptance": WalletAcceptance(wallets["dining_dollars"]["status"]),
        "dining_dollars_reason": wallets["dining_dollars"]["reason"],
        "dining_dollars_source": wallets["dining_dollars"]["source"],
        "triton_cash_acceptance": WalletAcceptance(wallets["triton_cash"]["status"]),
        "triton_cash_reason": wallets["triton_cash"]["reason"],
        "triton_cash_source": wallets["triton_cash"]["source"],
        "sources": [{"key": key, **catalog["sources"][key]} for key in venue["sources"]],
        "notes": list(venue["notes"]),
        "catalog_version": catalog["catalog_version"],
        "verified_on": date.fromisoformat(catalog["verified_on"]),
        "is_active": True,
    }


def _station_fields(venue: dict, name: str, catalog: dict) -> dict:
    # Only the station's name is verified; its own menu link and hours were not captured.
    hdh_sources = [key for key in venue["sources"] if key.startswith("hdh")]
    return {
        "venue_id": venue["id"],
        "name": name,
        "menu_url": None,
        "hours": None,
        "sources": [{"key": key, **catalog["sources"][key]} for key in hdh_sources],
        "catalog_version": catalog["catalog_version"],
        "verified_on": date.fromisoformat(catalog["verified_on"]),
        "is_active": True,
    }


@dataclass
class SeedResult:
    venues_inserted: int = 0
    venues_updated: int = 0
    venues_unchanged: int = 0
    venues_deactivated: int = 0
    stations_inserted: int = 0
    stations_updated: int = 0
    stations_unchanged: int = 0
    stations_deactivated: int = 0
    deactivated_ids: list[str] = field(default_factory=list)


def _upsert(session: Session, model, record_id: str, values: dict) -> str:
    existing = session.get(model, record_id)
    now = _now()
    if existing is None:
        session.add(model(id=record_id, created_at=now, updated_at=now, **values))
        return "inserted"
    changed = {key: value for key, value in values.items() if getattr(existing, key) != value}
    if not changed:
        return "unchanged"
    for key, value in changed.items():
        setattr(existing, key, value)
    existing.updated_at = now
    return "updated"


def seed_food_catalog(session: Session, catalog: Optional[dict] = None) -> SeedResult:
    """Make the database match the catalog. Repeatable; flushes but leaves committing to the caller."""
    catalog = catalog or load_catalog()
    result = SeedResult()
    venue_ids: set[str] = set()
    station_ids: set[str] = set()
    for venue in catalog["venues"]:
        outcome = _upsert(session, FoodVenue, venue["id"], _venue_fields(venue, catalog))
        setattr(result, f"venues_{outcome}", getattr(result, f"venues_{outcome}") + 1)
        venue_ids.add(venue["id"])
    session.flush()  # stations reference their venue
    for venue in catalog["venues"]:
        for name in venue["stations"]:
            identifier = station_id(venue["id"], name)
            if identifier in station_ids:
                raise ValueError(f"catalog has two stations with the ID {identifier!r}")
            station_ids.add(identifier)
            outcome = _upsert(session, FoodStation, identifier, _station_fields(venue, name, catalog))
            setattr(result, f"stations_{outcome}", getattr(result, f"stations_{outcome}") + 1)
    # Records that left the catalog stay (reviews may point at them) but are no longer active.
    for model, kept, counter in ((FoodStation, station_ids, "stations_deactivated"), (FoodVenue, venue_ids, "venues_deactivated")):
        for record in session.scalars(select(model).where(model.is_active.is_(True))):
            if record.id not in kept:
                record.is_active = False
                record.updated_at = _now()
                setattr(result, counter, getattr(result, counter) + 1)
                result.deactivated_ids.append(record.id)
    session.flush()
    return result


# --- Ratings (always aggregated from visible reviews; never stored) -----------------------------

@dataclass(frozen=True)
class RatingSummary:
    review_count: int
    average_rating: Optional[float]  # None means "No reviews yet", never 0


def _summaries(session: Session, column, ids: Iterable[str], target: ReviewTarget) -> dict[str, RatingSummary]:
    ids = list(ids)
    rows = session.execute(
        select(column, func.count(FoodReview.id), func.avg(FoodReview.rating))
        .where(column.in_(ids), FoodReview.target_type == target, FoodReview.moderation_state == ModerationState.visible)
        .group_by(column)
    ).all() if ids else []
    found = {key: RatingSummary(count, round(float(average), 2)) for key, count, average in rows}
    return {key: found.get(key, RatingSummary(0, None)) for key in ids}


def venue_ratings(session: Session, venue_ids: Iterable[str]) -> dict[str, RatingSummary]:
    """Each venue's average of its students' current star ratings (one per student per venue).
    Written reviews, dish reviews and chat messages never count."""
    ids = list(venue_ids)
    rows = session.execute(
        select(FoodVenueRating.venue_id, func.count(FoodVenueRating.id), func.avg(FoodVenueRating.rating))
        .where(FoodVenueRating.venue_id.in_(ids)).group_by(FoodVenueRating.venue_id)
    ).all() if ids else []
    found = {venue_id: RatingSummary(count, round(float(average), 2)) for venue_id, count, average in rows}
    return {venue_id: found.get(venue_id, RatingSummary(0, None)) for venue_id in ids}


def menu_item_ratings(session: Session, item_ids: Iterable[str]) -> dict[str, RatingSummary]:
    return _summaries(session, FoodReview.menu_item_id, item_ids, ReviewTarget.menu_item)


def item_belongs_to(session: Session, venue_id: str, station_id_: str, item_id: str) -> bool:
    """Application-level check of the review hierarchy (the database enforces it as well)."""
    return session.scalar(
        select(func.count(FoodMenuItem.id))
        .join(FoodStation, FoodStation.id == FoodMenuItem.station_id)
        .where(FoodMenuItem.id == item_id, FoodStation.id == station_id_, FoodStation.venue_id == venue_id)
    ) == 1
