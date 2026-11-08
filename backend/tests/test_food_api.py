"""Public Food Nearby catalog API, plus Food Chat data in account export (deletion: test_food_chat_deletion.py)."""

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.app import db
from backend.app.config import Settings, get_settings
from backend.app.db import Base, get_db
from backend.app.food_catalog import menu_name_key, seed_food_catalog
from backend.app.food_models import (
    FoodVenueRating,
    FoodComment,
    FoodCommentVote,
    FoodMenuAppearance,
    FoodMenuItem,
    FoodReport,
    FoodReview,
    FoodVenue,
    MenuAvailability,
    ReportReason,
    ReviewTarget,
)
from backend.app.main import app
from backend.app.models import Participant, UserAccount
from backend.tests.test_accounts import accept_consent, signup
from backend.tests.test_food_catalog import sqlite_engine

NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
SOURCE = "https://hdh-web.ucsd.edu/dining/apps/diningservices"


@pytest.fixture
def factory(monkeypatch):
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as session:
        seed_food_catalog(session)
        session.commit()
    settings = Settings(
        database_url="sqlite:///:memory:", environment="test", consent_version="v1",
        consent_document_url="https://example.test/consent/v1", session_secret="session-secret",
        csrf_secret="csrf-secret", cors_origins=("http://localhost:3000",),
    )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session_factory", lambda: session_factory)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    yield session_factory
    app.dependency_overrides.clear()


client = TestClient(app)  # no session cookie: the catalog is public


def get(path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def add_participant(factory):
    with factory() as session:
        value = Participant()
        session.add(value)
        session.commit()
        return value.id


def add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl", appearances=()):
    with factory() as session:
        item = FoodMenuItem(station_id=station, name=name, name_key=menu_name_key(name), source_url=SOURCE, verified_at=NOW, dietary_labels=None)
        session.add(item)
        session.flush()
        for day, period, price in appearances:
            session.add(FoodMenuAppearance(menu_item_id=item.id, menu_date=day, meal_period=period, price_cents=price,
                                           source_url=SOURCE, retrieved_at=NOW, last_verified_at=NOW))
        session.commit()
        return item.id


# 12. Venues ----------------------------------------------------------------------------------

def test_venue_list_is_public_paginated_and_filterable(factory):
    everything = get("/api/v1/food/venues")
    assert (everything["total"], len(everything["venues"]), everything["limit"], everything["offset"]) == (68, 68, 100, 0)
    names = [venue["name"] for venue in everything["venues"]]
    assert names == sorted(names)

    page = get("/api/v1/food/venues", limit=10, offset=60)
    assert (page["total"], len(page["venues"])) == (68, 8)
    assert get("/api/v1/food/venues", operator="hdh")["total"] == 16
    assert get("/api/v1/food/venues", kind="market")["total"] == 6
    assert get("/api/v1/food/venues", on_campus="false")["total"] == 13
    for bad in ({"operator": "grubhub"}, {"limit": 0}, {"limit": 201}, {"offset": -1}):
        assert client.get("/api/v1/food/venues", params=bad).status_code == 422


def test_venue_summary_reports_eligibility_location_and_no_reviews_honestly(factory):
    venues = {venue["id"]: venue for venue in get("/api/v1/food/venues")["venues"]}
    pines = venues["pines"]
    assert pines["wallets"]["dining_dollars"]["status"] == pines["wallets"]["triton_cash"]["status"] == "accepted"
    assert pines["coordinates"] == {"lat": 32.87886, "lng": -117.242592} and pines["has_published_hours"] is True
    assert pines["station_count"] == 8 and pines["rating"] == {"review_count": 0, "average_rating": None}
    melt = venues["the-melt"]
    assert melt["wallets"]["dining_dollars"] == {
        "status": "not_accepted", "reason": "Dining Dollars are only for HDH dining and market locations.", "source": "diningDollarsFaq",
    }
    assert (melt["coordinates"], melt["has_published_hours"], melt["station_count"]) == (None, False, 0)


def test_venue_detail_includes_stations_sources_and_hours(factory):
    venue = get("/api/v1/food/venues/64-degrees")
    assert [s["name"] for s in venue["stations"]] == ["Al Dente", "Garden Bar", "Taqueria", "Triton Grill", "Umi", "Wok This Way"]
    assert venue["stations"][3]["id"] == "64-degrees--triton-grill" and venue["stations"][3]["menu_item_count"] == 0
    assert venue["hours"]["sat"] == [["09:00", "21:00"]] and venue["verified_on"] == "2026-10-30"
    assert {s["key"] for s in venue["sources"]} == {"hdhMenus", "hdhRestaurants", "campusMap"}
    assert venue["catalog_version"] == "food-venues.2026-10-30"
    assert client.get("/api/v1/food/venues/no-such-venue").status_code == 404


def test_inactive_venues_are_hidden_from_lists_but_still_readable(factory):
    with factory() as session:
        session.get(FoodVenue, "bistro").is_active = False
        session.commit()
    assert get("/api/v1/food/venues")["total"] == 67
    assert get("/api/v1/food/venues", include_inactive="true")["total"] == 68
    assert get("/api/v1/food/venues/bistro")["is_active"] is False


# 12. Stations, menu items, appearances --------------------------------------------------------

def test_stations_belong_to_their_venue(factory):
    stations = get("/api/v1/food/venues/pines/stations")
    assert stations["venue_id"] == "pines" and "pines--slice-at-pines" in [s["id"] for s in stations["stations"]]
    assert get("/api/v1/food/venues/the-melt/stations")["stations"] == []
    station = get("/api/v1/food/stations/pines--slice-at-pines")
    assert (station["name"], station["venue"], station["menu_url"], station["hours"]) == (
        "Slice at Pines",
        # A station has no menu page of its own; it carries its venue's official menu link.
        {"id": "pines", "name": "Pines", "menu_url": "https://hdh-web.ucsd.edu/dining/apps/diningservices/Restaurants/Venue_V3?locId=3&locDetID=6&dayNum=0"},
        None, None,
    )
    assert client.get("/api/v1/food/venues/nowhere/stations").status_code == 404
    assert client.get("/api/v1/food/stations/nowhere").status_code == 404


def test_an_empty_menu_says_no_verified_data_instead_of_inventing_items(factory):
    menu = get("/api/v1/food/stations/64-degrees--triton-grill/menu-items")
    assert menu == {"station_id": "64-degrees--triton-grill", "menu_status": "no_verified_menu_data", "items": [], "total": 0, "limit": 100, "offset": 0}


def test_menu_items_and_dated_appearances_with_known_and_unknown_prices(factory):
    item_id = add_item(factory, appearances=[
        (date(2026, 11, 2), "lunch", 1_095), (date(2026, 11, 5), "lunch", None), (date(2026, 11, 5), "dinner", 1_150),
    ])
    menu = get("/api/v1/food/stations/64-degrees--triton-grill/menu-items")
    assert menu["menu_status"] == "verified_items" and menu["total"] == 1
    item = menu["items"][0]
    assert (item["id"], item["name"], item["dietary_labels"], item["rating"]) == (item_id, "Chicken Rice Bowl", None, {"review_count": 0, "average_rating": None})
    assert get("/api/v1/food/venues/64-degrees")["stations"][3]["menu_item_count"] == 1

    history = get(f"/api/v1/food/menu-items/{item_id}/appearances")
    assert [(a["menu_date"], a["meal_period"], a["price_cents"], a["price_status"]) for a in history["appearances"]] == [
        ("2026-11-05", "dinner", 1_150, "verified"), ("2026-11-05", "lunch", None, "unknown"), ("2026-11-02", "lunch", 1_095, "verified"),
    ]
    assert {a["availability"] for a in history["appearances"]} == {MenuAvailability.unknown.value}
    assert history["appearances"][0]["retrieved_at"].endswith("Z")
    ranged = get(f"/api/v1/food/menu-items/{item_id}/appearances", **{"from": "2026-11-03", "to": "2026-11-30"})
    assert ranged["total"] == 2
    assert get(f"/api/v1/food/menu-items/{item_id}/appearances", limit=1)["total"] == 3
    assert client.get(f"/api/v1/food/menu-items/{item_id}/appearances", params={"from": "2026-11-09", "to": "2026-11-01"}).status_code == 422
    assert client.get("/api/v1/food/menu-items/missing/appearances").status_code == 404


def test_venue_ratings_come_only_from_star_ratings(factory):
    item_id = add_item(factory)
    first, second, third = add_participant(factory), add_participant(factory), add_participant(factory)
    with factory() as session:
        session.add_all([
            FoodVenueRating(participant_id=first, venue_id="64-degrees", rating=4),
            FoodVenueRating(participant_id=second, venue_id="64-degrees", rating=3),
            FoodVenueRating(participant_id=third, venue_id="64-degrees", rating=4),
            # Older written reviews (venue or dish) no longer count toward a venue's rating.
            FoodReview(participant_id=first, target_type=ReviewTarget.venue, venue_id="64-degrees", rating=1, body=""),
            FoodReview(participant_id=first, target_type=ReviewTarget.menu_item, venue_id="64-degrees",
                       station_id="64-degrees--triton-grill", menu_item_id=item_id, rating=1, body=""),
        ])
        session.commit()
    assert get("/api/v1/food/venues/64-degrees")["rating"] == {"review_count": 3, "average_rating": 3.67}  # (4+3+4)/3
    assert get("/api/v1/food/venues/pines")["rating"] == {"review_count": 0, "average_rating": None}
    assert get("/api/v1/food/stations/64-degrees--triton-grill/menu-items")["items"][0]["rating"] == {"review_count": 1, "average_rating": 1.0}


# 13. Account export and deletion ----------------------------------------------------------------

def test_export_includes_only_the_participants_own_food_chat_content(factory):
    alice = TestClient(app)
    assert signup(alice).status_code == 201
    accept_consent(alice)
    other = add_participant(factory)
    with factory() as session:
        me = session.scalar(select(UserAccount.participant_id))
        review = FoodReview(participant_id=me, target_type=ReviewTarget.venue, venue_id="pines", rating=5, body="Great pizza")
        theirs = FoodReview(participant_id=other, target_type=ReviewTarget.venue, venue_id="pines", rating=1, body="Not mine")
        session.add_all([review, theirs])
        session.flush()
        comment = FoodComment(review_id=theirs.id, participant_id=me, body="I disagree")
        session.add(comment)
        session.flush()
        session.add_all([
            FoodCommentVote(comment_id=comment.id, participant_id=other, value=1),  # someone else's vote
            FoodReport(participant_id=me, review_id=theirs.id, reason=ReportReason.misinformation),
        ])
        session.commit()

    export = alice.get("/api/v1/pilot/export").json()
    assert export["schema_version"] == "stage8.v1"
    chat = export["food_chat"]
    assert [(r["venue_id"], r["rating"], r["body"]) for r in chat["reviews"]] == [("pines", 5, "Great pizza")]
    assert [c["body"] for c in chat["comments"]] == ["I disagree"]
    assert chat["comment_votes"] == []
    assert [(r["review_id"], r["reason"], r["status"]) for r in chat["reports"]] == [(theirs.id, "misinformation", "open")]
