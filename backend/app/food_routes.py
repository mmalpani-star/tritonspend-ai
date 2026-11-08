"""Public, read-only Food Nearby catalog API: Venue -> Station -> Menu Item -> Menu Appearance.

No authentication: everything here is official catalog data or aggregate ratings, never a
participant's own records. Empty menus are reported as "no_verified_menu_data", never filled.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .food_catalog import RatingSummary, menu_item_ratings, venue_ratings
from .food_models import FoodMenuAppearance, FoodMenuItem, FoodStation, FoodVenue, VenueKind, VenueOperator
from .food_schemas import (
    MenuAppearanceListOut,
    MenuAppearanceOut,
    MenuItemListOut,
    MenuItemOut,
    StationDetailOut,
    StationListOut,
    StationSummaryOut,
    VenueDetailOut,
    VenueListOut,
    VenueSummaryOut,
)

router = APIRouter(prefix="/api/v1/food", tags=["food"])

MAX_VENUES_PAGE = 200
MAX_MENU_ITEMS_PAGE = 500
MAX_APPEARANCES = 366


def _rating(summary: RatingSummary) -> dict:
    return {"review_count": summary.review_count, "average_rating": summary.average_rating}


def _wallet(status, reason: str, source: Optional[str]) -> dict:
    return {"status": status.value, "reason": reason, "source": source}


def _counts(session: Session, column, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    rows = session.execute(select(column, func.count()).where(column.in_(ids)).group_by(column)).all()
    return dict(rows)


def _station_counts(session: Session, venue_ids: list[str]) -> dict[str, int]:
    if not venue_ids:
        return {}
    rows = session.execute(
        select(FoodStation.venue_id, func.count())
        .where(FoodStation.venue_id.in_(venue_ids), FoodStation.is_active.is_(True))
        .group_by(FoodStation.venue_id)
    ).all()
    return dict(rows)


def _venue_summary(venue: FoodVenue, station_count: int, rating: RatingSummary) -> dict:
    return {
        "id": venue.id,
        "name": venue.name,
        "operator": venue.operator.value,
        "kind": venue.kind.value,
        "summary": venue.summary,
        "campus_area": venue.campus_area,
        "location": venue.location,
        "on_campus": venue.on_campus,
        "coordinates": {"lat": venue.latitude, "lng": venue.longitude} if venue.latitude is not None else None,
        "has_published_hours": venue.hours is not None,
        "wallets": {
            "dining_dollars": _wallet(venue.dining_dollars_acceptance, venue.dining_dollars_reason, venue.dining_dollars_source),
            "triton_cash": _wallet(venue.triton_cash_acceptance, venue.triton_cash_reason, venue.triton_cash_source),
        },
        "station_count": station_count,
        "rating": _rating(rating),
        "is_active": venue.is_active,
        "verified_on": venue.verified_on,
    }


def _station_summary(station: FoodStation, item_count: int) -> dict:
    return {
        "id": station.id,
        "venue_id": station.venue_id,
        "name": station.name,
        "menu_url": station.menu_url,
        "hours": station.hours,
        "is_active": station.is_active,
        "verified_on": station.verified_on,
        "menu_item_count": item_count,
    }


def _get_or_404(session: Session, model, identifier: str, label: str):
    record = session.get(model, identifier)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


def _active_stations(session: Session, venue_id: str) -> list[FoodStation]:
    return list(session.scalars(
        select(FoodStation)
        .where(FoodStation.venue_id == venue_id, FoodStation.is_active.is_(True))
        .order_by(FoodStation.name, FoodStation.id)
    ))


@router.get("/venues", response_model=VenueListOut)
def list_venues(
    operator: Optional[VenueOperator] = Query(None),
    kind: Optional[VenueKind] = Query(None),
    on_campus: Optional[bool] = Query(None),
    include_inactive: bool = Query(False),
    limit: int = Query(100, ge=1, le=MAX_VENUES_PAGE),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> VenueListOut:
    conditions = []
    if operator is not None:
        conditions.append(FoodVenue.operator == operator)
    if kind is not None:
        conditions.append(FoodVenue.kind == kind)
    if on_campus is not None:
        conditions.append(FoodVenue.on_campus.is_(on_campus))
    if not include_inactive:
        conditions.append(FoodVenue.is_active.is_(True))
    total = session.scalar(select(func.count()).select_from(FoodVenue).where(*conditions))
    venues = list(session.scalars(
        select(FoodVenue).where(*conditions).order_by(FoodVenue.name, FoodVenue.id).limit(limit).offset(offset)
    ))
    ids = [venue.id for venue in venues]
    stations = _station_counts(session, ids)
    ratings = venue_ratings(session, ids)
    return VenueListOut(
        venues=[_venue_summary(venue, stations.get(venue.id, 0), ratings[venue.id]) for venue in venues],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/venues/{venue_id}", response_model=VenueDetailOut)
def read_venue(venue_id: str, session: Session = Depends(get_db)) -> VenueDetailOut:
    venue = _get_or_404(session, FoodVenue, venue_id, "venue")
    stations = _active_stations(session, venue.id)
    items = _counts(session, FoodMenuItem.station_id, [station.id for station in stations])
    return VenueDetailOut(
        **_venue_summary(venue, len(stations), venue_ratings(session, [venue.id])[venue.id]),
        description=venue.description,
        tags=venue.tags,
        hours=venue.hours,
        menu_url=venue.menu_url,
        website_url=venue.website_url,
        coordinates_source=venue.coordinates_source,
        sources=venue.sources,
        notes=venue.notes,
        catalog_version=venue.catalog_version,
        stations=[_station_summary(station, items.get(station.id, 0)) for station in stations],
    )


@router.get("/venues/{venue_id}/stations", response_model=StationListOut)
def list_venue_stations(venue_id: str, session: Session = Depends(get_db)) -> StationListOut:
    venue = _get_or_404(session, FoodVenue, venue_id, "venue")
    stations = _active_stations(session, venue.id)
    items = _counts(session, FoodMenuItem.station_id, [station.id for station in stations])
    return StationListOut(venue_id=venue.id, stations=[_station_summary(station, items.get(station.id, 0)) for station in stations])


@router.get("/stations/{station_id}", response_model=StationDetailOut)
def read_station(station_id: str, session: Session = Depends(get_db)) -> StationDetailOut:
    station = _get_or_404(session, FoodStation, station_id, "station")
    venue = session.get(FoodVenue, station.venue_id)
    item_count = session.scalar(select(func.count()).select_from(FoodMenuItem).where(FoodMenuItem.station_id == station.id))
    return StationDetailOut(
        **_station_summary(station, item_count),
        venue={"id": venue.id, "name": venue.name, "menu_url": venue.menu_url},
        sources=station.sources,
        catalog_version=station.catalog_version,
    )


@router.get("/stations/{station_id}/menu-items", response_model=MenuItemListOut)
def list_station_menu_items(
    station_id: str,
    limit: int = Query(100, ge=1, le=MAX_MENU_ITEMS_PAGE),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> MenuItemListOut:
    station = _get_or_404(session, FoodStation, station_id, "station")
    condition = (FoodMenuItem.station_id == station.id, FoodMenuItem.is_active.is_(True))
    total = session.scalar(select(func.count()).select_from(FoodMenuItem).where(*condition))
    items = list(session.scalars(
        select(FoodMenuItem).where(*condition).order_by(FoodMenuItem.name, FoodMenuItem.id).limit(limit).offset(offset)
    ))
    ratings = menu_item_ratings(session, [item.id for item in items])
    return MenuItemListOut(
        station_id=station.id,
        menu_status="verified_items" if total else "no_verified_menu_data",
        items=[
            MenuItemOut(
                id=item.id,
                station_id=item.station_id,
                name=item.name,
                description=item.description,
                dietary_labels=item.dietary_labels,
                allergens=item.allergens,
                source_url=item.source_url,
                verified_at=item.verified_at,
                is_active=item.is_active,
                rating=_rating(ratings[item.id]),
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/menu-items/{menu_item_id}/appearances", response_model=MenuAppearanceListOut)
def list_menu_item_appearances(
    menu_item_id: str,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    limit: int = Query(60, ge=1, le=MAX_APPEARANCES),
    session: Session = Depends(get_db),
) -> MenuAppearanceListOut:
    item = _get_or_404(session, FoodMenuItem, menu_item_id, "menu item")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="from must be on or before to")
    conditions = [FoodMenuAppearance.menu_item_id == item.id]
    if date_from:
        conditions.append(FoodMenuAppearance.menu_date >= date_from)
    if date_to:
        conditions.append(FoodMenuAppearance.menu_date <= date_to)
    total = session.scalar(select(func.count()).select_from(FoodMenuAppearance).where(*conditions))
    appearances = session.scalars(
        select(FoodMenuAppearance)
        .where(*conditions)
        .order_by(FoodMenuAppearance.menu_date.desc(), FoodMenuAppearance.meal_period)
        .limit(limit)
    )
    return MenuAppearanceListOut(
        menu_item_id=item.id,
        appearances=[
            MenuAppearanceOut(
                id=value.id,
                menu_item_id=value.menu_item_id,
                menu_date=value.menu_date,
                meal_period=value.meal_period,
                price_cents=value.price_cents,
                price_status="verified" if value.price_cents is not None else "unknown",
                currency=value.currency,
                availability=value.availability.value,
                source_url=value.source_url,
                retrieved_at=value.retrieved_at,
                last_verified_at=value.last_verified_at,
            )
            for value in appearances
        ],
        total=total,
        limit=limit,
    )
