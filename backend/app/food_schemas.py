"""Response models for the public, read-only Food Nearby catalog API."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel

from .pilot_schemas import UtcDateTime

Acceptance = Literal["accepted", "not_accepted", "not_verified"]


class WalletEligibilityOut(BaseModel):
    status: Acceptance
    reason: str
    source: Optional[str] = None


class WalletsOut(BaseModel):
    dining_dollars: WalletEligibilityOut
    triton_cash: WalletEligibilityOut


class CoordinatesOut(BaseModel):
    lat: float
    lng: float


class SourceOut(BaseModel):
    key: str
    label: str
    url: str


class RatingOut(BaseModel):
    review_count: int
    # null means "No reviews yet" (never 0/5)
    average_rating: Optional[float] = None


class StationSummaryOut(BaseModel):
    id: str
    venue_id: str
    name: str
    menu_url: Optional[str] = None
    hours: Optional[dict] = None
    is_active: bool
    verified_on: date
    menu_item_count: int


class VenueSummaryOut(BaseModel):
    id: str
    name: str
    operator: Literal["hdh", "triton_cash_partner"]
    kind: Literal["restaurant", "market", "merchant"]
    summary: Optional[str] = None
    campus_area: Optional[str] = None
    location: Optional[str] = None
    on_campus: bool
    coordinates: Optional[CoordinatesOut] = None
    has_published_hours: bool
    wallets: WalletsOut
    station_count: int
    rating: RatingOut
    is_active: bool
    verified_on: date


class VenueDetailOut(VenueSummaryOut):
    description: Optional[str] = None
    tags: list[str]
    hours: Optional[dict] = None
    menu_url: Optional[str] = None
    website_url: Optional[str] = None
    coordinates_source: Optional[dict] = None
    sources: list[SourceOut]
    notes: list[str]
    catalog_version: str
    stations: list[StationSummaryOut]


class VenueListOut(BaseModel):
    venues: list[VenueSummaryOut]
    total: int
    limit: int
    offset: int


class StationListOut(BaseModel):
    venue_id: str
    stations: list[StationSummaryOut]


class VenueRefOut(BaseModel):
    id: str
    name: str


class StationVenueOut(VenueRefOut):
    # The venue's official menu page (HDH publishes menus per venue, not per station).
    menu_url: Optional[str] = None


class StationDetailOut(StationSummaryOut):
    venue: StationVenueOut
    sources: list[SourceOut]
    catalog_version: str


class MenuItemOut(BaseModel):
    id: str
    station_id: str
    name: str
    description: Optional[str] = None
    dietary_labels: Optional[list[str]] = None
    allergens: Optional[list[str]] = None
    source_url: str
    verified_at: UtcDateTime
    is_active: bool
    rating: RatingOut


MenuStatus = Literal["no_verified_menu_data", "verified_items"]


class MenuItemListOut(BaseModel):
    station_id: str
    # "no_verified_menu_data": nothing has been imported from a verified source, not "no food here".
    menu_status: MenuStatus
    items: list[MenuItemOut]
    total: int
    limit: int
    offset: int


class MenuAppearanceOut(BaseModel):
    id: str
    menu_item_id: str
    menu_date: date
    meal_period: str
    price_cents: Optional[int] = None
    price_status: Literal["verified", "unknown"]
    currency: str
    # Being listed on a menu does not mean available right now.
    availability: Literal["unknown", "available", "sold_out", "unavailable"]
    source_url: str
    retrieved_at: UtcDateTime
    last_verified_at: UtcDateTime


class MenuAppearanceListOut(BaseModel):
    menu_item_id: str
    appearances: list[MenuAppearanceOut]
    total: int
    limit: int
