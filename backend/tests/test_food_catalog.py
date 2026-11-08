"""Food Nearby persistence: catalog seeding, the Venue -> Station -> Item -> Appearance hierarchy,
Food Chat integrity rules, rating aggregation, migration parity, and account export.

SQLite only enforces foreign keys with PRAGMA foreign_keys=ON, so these engines turn it on
(PostgreSQL always enforces them; see test_postgres_integration.py).
"""

import copy
from datetime import date, datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.food_catalog import (
    load_catalog,
    menu_item_ratings,
    menu_name_key,
    item_belongs_to,
    seed_food_catalog,
    station_id,
    venue_ratings,
)
from backend.app.food_models import (
    FoodVenueRating,
    FoodComment,
    FoodCommentVote,
    FoodMenuAppearance,
    FoodMenuItem,
    FoodReport,
    FoodReview,
    FoodStation,
    FoodVenue,
    MenuAvailability,
    ModerationState,
    ReportReason,
    ReviewTarget,
    WalletAcceptance,
)
from backend.app.models import Participant

NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
SOURCE = "https://hdh-web.ucsd.edu/dining/apps/diningservices"


def sqlite_engine(url="sqlite:///:memory:"):
    engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture
def session():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as value:
        seed_food_catalog(value)
        value.commit()
        yield value


def count(session, model, *where):
    return session.scalar(select(func.count()).select_from(model).where(*where))


def participant(session):
    value = Participant()
    session.add(value)
    session.flush()
    return value.id


def menu_item(session, station="64-degrees--triton-grill", name="Chicken Rice Bowl"):
    value = FoodMenuItem(station_id=station, name=name, name_key=menu_name_key(name), source_url=SOURCE, verified_at=NOW)
    session.add(value)
    session.flush()
    return value


def rejected(session, *records):
    """Flush inside a savepoint and expect the database to refuse it."""
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add_all(records)
            session.flush()


def venue_review(session, author, venue="64-degrees", rating=4, **extra):
    return FoodReview(participant_id=author, target_type=ReviewTarget.venue, venue_id=venue, rating=rating, body="Good", **extra)


def dish_review(session, author, item, venue="64-degrees", station=None, rating=5):
    return FoodReview(
        participant_id=author, target_type=ReviewTarget.menu_item, venue_id=venue,
        station_id=station or item.station_id, menu_item_id=item.id, rating=rating, body="Tasty",
    )


# 1. Catalog seeding --------------------------------------------------------------------------

def test_seed_inserts_the_whole_official_catalog_with_unknowns_kept_unknown(session):
    catalog = load_catalog()
    assert count(session, FoodVenue) == len(catalog["venues"]) == 68
    assert count(session, FoodStation) == sum(len(v["stations"]) for v in catalog["venues"]) == 45
    assert count(session, FoodVenue, FoodVenue.operator == "hdh") == 16
    assert count(session, FoodVenue, FoodVenue.on_campus.is_(False)) == 13
    assert count(session, FoodVenue, FoodVenue.latitude.is_not(None)) == 47
    assert count(session, FoodVenue, FoodVenue.hours.is_not(None)) == 16
    assert count(session, FoodMenuItem) == count(session, FoodMenuAppearance) == 0  # nothing invented

    degrees = session.get(FoodVenue, "64-degrees")
    assert (degrees.latitude, degrees.longitude) == (32.874786, -117.242043)
    assert degrees.coordinates_source == {"layer": "Dining_Halls", "feature": "64 Degrees", "building": "64 Degrees"}
    assert degrees.hours["fri"] == [["07:00", "21:00"]]
    assert degrees.menu_url.startswith("https://hdh-web.ucsd.edu/")
    assert (degrees.dining_dollars_acceptance, degrees.triton_cash_acceptance) == (WalletAcceptance.accepted, WalletAcceptance.accepted)
    assert degrees.verified_on == date(2026, 10, 30) and degrees.catalog_version == "food-venues.2026-10-30"
    assert {s["key"] for s in degrees.sources} == {"hdhMenus", "hdhRestaurants", "campusMap"}

    melt = session.get(FoodVenue, "the-melt")  # off campus: nothing verified beyond the listing
    assert (melt.latitude, melt.longitude, melt.hours, melt.location, melt.website_url) == (None, None, None, None, None)
    assert melt.dining_dollars_acceptance == WalletAcceptance.not_accepted
    assert melt.dining_dollars_source == "diningDollarsFaq"
    assert melt.triton_cash_acceptance == WalletAcceptance.accepted
    assert melt.campus_area == "La Jolla/UTC" and melt.on_campus is False
    espresso = session.get(FoodVenue, "art-of-espresso")
    assert espresso.latitude is None and espresso.notes  # conflicting map data stays unresolved, with the note
    # The catalog never claims a wallet it can't support.
    assert count(session, FoodVenue, FoodVenue.operator == "triton_cash_partner",
                 FoodVenue.dining_dollars_acceptance == WalletAcceptance.accepted) == 0


def test_station_ids_are_deterministic_and_only_catalog_names_are_seeded(session):
    assert station_id("pines", "Slice at Pines") == "pines--slice-at-pines"
    assert station_id("canyon-vista-marketplace", "Earl's Coffeehouse") == "canyon-vista-marketplace--earls-coffeehouse"
    pines = session.scalars(select(FoodStation.name).where(FoodStation.venue_id == "pines").order_by(FoodStation.name)).all()
    assert pines == ["Breeze", "Char", "Current", "Heat", "Morning Fog", "Pacific Coast Hwy", "Slice at Pines", "Street Eats"]
    grill = session.get(FoodStation, "64-degrees--triton-grill")
    assert grill.venue_id == "64-degrees" and grill.menu_url is None and grill.hours is None  # not verified per station
    assert count(session, FoodStation, FoodStation.venue_id.in_(["the-melt", "panda-express"])) == 0


# 2. Repeated seeding ---------------------------------------------------------------------------

def test_reseeding_is_idempotent_and_never_duplicates(session):
    again = seed_food_catalog(session)
    session.commit()
    assert (again.venues_inserted, again.venues_updated, again.venues_unchanged) == (0, 0, 68)
    assert (again.stations_inserted, again.stations_updated, again.stations_unchanged) == (0, 0, 45)
    session.expire_all()  # compare against values read back from the database, not the identity map
    assert seed_food_catalog(session).venues_unchanged == 68
    assert (count(session, FoodVenue), count(session, FoodStation)) == (68, 45)


def test_catalog_changes_update_or_deactivate_but_never_delete(session):
    author = participant(session)
    session.add(venue_review(session, author, venue="bistro"))
    session.commit()
    catalog = copy.deepcopy(load_catalog())
    catalog["venues"] = [v for v in catalog["venues"] if v["id"] != "bistro"]  # venue leaves the catalog
    pines = next(v for v in catalog["venues"] if v["id"] == "pines")
    pines["stations"] = [s for s in pines["stations"] if s != "Breeze"]  # a station leaves
    pines["summary"] = "Updated summary"

    result = seed_food_catalog(session, catalog)
    session.commit()

    assert (result.venues_updated, result.venues_deactivated, result.stations_deactivated) == (1, 1, 3)  # bistro's 2 + Breeze
    assert sorted(result.deactivated_ids) == ["bistro", "bistro--the-bistro", "bistro--the-bistro-sushi", "pines--breeze"]
    assert session.get(FoodVenue, "bistro").is_active is False and count(session, FoodReview) == 1  # review kept
    assert session.get(FoodVenue, "pines").summary == "Updated summary"
    assert (count(session, FoodVenue), count(session, FoodStation)) == (68, 45)

    restored = seed_food_catalog(session)  # back in the catalog: reactivated, not duplicated
    assert restored.venues_updated == 2 and restored.stations_updated == 3
    assert session.get(FoodVenue, "bistro").is_active is True


# 3-4. Hierarchy --------------------------------------------------------------------------------

def test_stations_must_belong_to_a_real_venue_with_unique_names(session):
    rejected(session, FoodStation(id="nowhere--grill", venue_id="nowhere", name="Grill", sources=[], catalog_version="t", verified_on=date(2026, 1, 1)))
    rejected(session, FoodStation(id="pines--slice-2", venue_id="pines", name="Slice at Pines", sources=[], catalog_version="t", verified_on=date(2026, 1, 1)))


def test_menu_items_belong_to_one_station_with_a_stable_name_identity(session):
    item = menu_item(session)
    assert menu_name_key("  Chicken   RICE bowl ") == menu_name_key("Chicken Rice Bowl") == "chicken rice bowl"
    rejected(session, FoodMenuItem(station_id=item.station_id, name="chicken rice BOWL", name_key=menu_name_key("chicken rice BOWL"), source_url=SOURCE, verified_at=NOW))
    menu_item(session, station="pines--slice-at-pines")  # same name at another station is a different dish
    rejected(session, FoodMenuItem(station_id="no-such-station", name="X", name_key="x", source_url=SOURCE, verified_at=NOW))
    rejected(session, FoodMenuItem(station_id=item.station_id, name="", name_key="", source_url=SOURCE, verified_at=NOW))
    assert item_belongs_to(session, "64-degrees", "64-degrees--triton-grill", item.id)
    assert not item_belongs_to(session, "pines", "64-degrees--triton-grill", item.id)


# 5-6. Appearances ------------------------------------------------------------------------------

def appearance(item, day, period="lunch", **extra):
    return FoodMenuAppearance(menu_item_id=item.id, menu_date=day, meal_period=period, source_url=SOURCE, retrieved_at=NOW, last_verified_at=NOW, **extra)


def test_appearances_keep_one_item_across_dates_with_their_own_prices(session):
    item = menu_item(session)
    session.add_all([appearance(item, date(2026, 11, 2), price_cents=1_095), appearance(item, date(2026, 11, 5), price_cents=1_150)])
    session.flush()
    rows = session.execute(
        select(FoodMenuAppearance.menu_date, FoodMenuAppearance.price_cents, FoodMenuAppearance.currency)
        .where(FoodMenuAppearance.menu_item_id == item.id).order_by(FoodMenuAppearance.menu_date)
    ).all()
    assert rows == [(date(2026, 11, 2), 1_095, "USD"), (date(2026, 11, 5), 1_150, "USD")]
    assert count(session, FoodMenuItem) == 1  # one dish, two dated appearances

    rejected(session, appearance(item, date(2026, 11, 2)))  # same item, date and meal period
    session.add(appearance(item, date(2026, 11, 2), period="dinner"))
    rejected(session, appearance(item, date(2026, 11, 3), price_cents=-1))
    rejected(session, appearance(item, date(2026, 11, 3), currency="EUR"))
    rejected(session, appearance(item, date(2026, 11, 3), period=""))
    rejected(session, FoodMenuAppearance(menu_item_id="missing", menu_date=date(2026, 11, 3), meal_period="lunch", source_url=SOURCE, retrieved_at=NOW, last_verified_at=NOW))


def test_unknown_price_and_availability_stay_unknown(session):
    item = menu_item(session)
    value = appearance(item, date(2026, 11, 6))
    session.add(value)
    session.flush()
    session.expire(value)
    assert value.price_cents is None and value.availability == MenuAvailability.unknown  # listed is not "available"
    rejected(session, appearance(item, date(2026, 11, 7), availability="maybe"))


# 7-8. Reviews ----------------------------------------------------------------------------------

def test_venue_and_dish_reviews_keep_the_hierarchy_consistent(session):
    author = participant(session)
    item = menu_item(session)
    session.add_all([venue_review(session, author), dish_review(session, author, item)])
    session.flush()

    # A venue review can't point at a station or item; a dish review must point at both.
    rejected(session, venue_review(session, participant(session), station_id="64-degrees--triton-grill"))
    rejected(session, FoodReview(participant_id=participant(session), target_type=ReviewTarget.menu_item, venue_id="64-degrees", rating=3, body=""))
    rejected(session, FoodReview(participant_id=participant(session), target_type=ReviewTarget.menu_item, venue_id="64-degrees", station_id="64-degrees--triton-grill", rating=3, body=""))
    # The station must belong to the venue, and the item to the station.
    rejected(session, dish_review(session, participant(session), item, venue="pines"))
    rejected(session, dish_review(session, participant(session), item, station="64-degrees--al-dente"))
    for rating in (0, 6):
        rejected(session, venue_review(session, participant(session), rating=rating))
    rejected(session, venue_review(session, participant(session), venue="no-such-venue"))


def test_one_review_per_participant_per_target_and_it_can_be_updated(session):
    author, other = participant(session), participant(session)
    item = menu_item(session)
    first = venue_review(session, author, rating=2)
    session.add_all([first, dish_review(session, author, item), venue_review(session, other)])
    session.flush()

    rejected(session, venue_review(session, author, rating=5))
    rejected(session, dish_review(session, author, item, rating=1))
    first.rating, first.body, first.updated_at = 5, "Changed my mind", NOW
    session.flush()
    assert count(session, FoodReview, FoodReview.participant_id == author) == 2
    session.add(venue_review(session, author, venue="pines"))  # a different venue is a different target
    session.flush()


def test_venue_and_dish_ratings_are_aggregated_separately_and_never_stored(session):
    authors = [participant(session) for _ in range(3)]
    item = menu_item(session)
    session.add_all([
        FoodVenueRating(participant_id=authors[0], venue_id="64-degrees", rating=4),
        FoodVenueRating(participant_id=authors[1], venue_id="64-degrees", rating=5),
        venue_review(session, authors[2], rating=1),  # an older written review: not a venue rating
        dish_review(session, authors[0], item, rating=2),
    ])
    session.flush()

    venues = venue_ratings(session, ["64-degrees", "pines"])
    assert (venues["64-degrees"].review_count, venues["64-degrees"].average_rating) == (2, 4.5)  # only star ratings count
    assert (venues["pines"].review_count, venues["pines"].average_rating) == (0, None)  # "No reviews yet", not 0
    dishes = menu_item_ratings(session, [item.id])
    assert (dishes[item.id].review_count, dishes[item.id].average_rating) == (1, 2.0)
    assert not {"average_rating", "review_count"} & {c["name"] for c in inspect(session.bind).get_columns("food_venues")}


# 9-11. Comments, votes, reports ---------------------------------------------------------------

def thread(session):
    author = participant(session)
    review, other_review = venue_review(session, author), venue_review(session, author, venue="pines")
    session.add_all([review, other_review])
    session.flush()
    top = FoodComment(review_id=review.id, participant_id=author, body="First")
    session.add(top)
    session.flush()
    return author, review, other_review, top


def test_replies_stay_inside_their_review_thread(session):
    author, review, other_review, top = thread(session)
    reply = FoodComment(review_id=review.id, parent_id=top.id, participant_id=participant(session), body="Agreed")
    session.add(reply)
    session.flush()
    session.add(FoodComment(review_id=review.id, parent_id=reply.id, participant_id=author, body="Nested reply"))
    session.flush()

    rejected(session, FoodComment(review_id=other_review.id, parent_id=top.id, participant_id=author, body="Wrong thread"))
    rejected(session, FoodComment(id="self", review_id=review.id, parent_id="self", participant_id=author, body="Me"))
    rejected(session, FoodComment(review_id=review.id, parent_id="missing", participant_id=author, body="Orphan"))
    rejected(session, FoodComment(review_id=review.id, participant_id=author, body=""))


def test_one_vote_per_participant_per_comment_which_can_change(session):
    _, _, _, top = thread(session)
    voter = participant(session)
    vote = FoodCommentVote(comment_id=top.id, participant_id=voter, value=1)
    session.add(vote)
    session.flush()
    rejected(session, FoodCommentVote(comment_id=top.id, participant_id=voter, value=-1))
    vote.value = -1
    session.flush()
    assert session.scalar(select(func.sum(FoodCommentVote.value)).where(FoodCommentVote.comment_id == top.id)) == -1
    rejected(session, FoodCommentVote(comment_id=top.id, participant_id=participant(session), value=2))
    rejected(session, FoodCommentVote(comment_id="missing", participant_id=voter, value=1))


def test_reports_target_exactly_one_real_review_or_comment(session):
    _, review, _, top = thread(session)
    reporter = participant(session)
    session.add_all([
        FoodReport(participant_id=reporter, review_id=review.id, reason=ReportReason.spam),
        FoodReport(participant_id=reporter, comment_id=top.id, reason=ReportReason.harassment, details="Rude"),
    ])
    session.flush()

    rejected(session, FoodReport(participant_id=reporter, reason=ReportReason.other))  # no target
    rejected(session, FoodReport(participant_id=participant(session), review_id=review.id, comment_id=top.id, reason=ReportReason.other))
    rejected(session, FoodReport(participant_id=reporter, review_id=review.id, reason=ReportReason.hate))  # duplicate
    rejected(session, FoodReport(participant_id=participant(session), comment_id="missing", reason=ReportReason.spam))
    rejected(session, FoodReport(participant_id=participant(session), review_id=review.id, reason="rude"))
    assert count(session, FoodReport) == 2


# Migration parity -------------------------------------------------------------------------------

FOOD_TABLES = [table for table in Base.metadata.sorted_tables if table.name.startswith("food_")]


def _shape(database, name):
    return {
        "columns": {c["name"]: (str(c["type"]).split("(")[0].replace("VARCHAR", "STRING"), c["nullable"]) for c in database.get_columns(name)},
        "foreign_keys": sorted((tuple(k["constrained_columns"]), k["referred_table"], tuple(k["referred_columns"])) for k in database.get_foreign_keys(name)),
        "unique": sorted(tuple(u["column_names"]) for u in database.get_unique_constraints(name)),
        "indexes": sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in database.get_indexes(name)),
        "checks": sorted(c["name"] for c in database.get_check_constraints(name)),
    }


def test_migration_creates_exactly_the_model_schema_and_downgrades_cleanly(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'food.db'}"  # disposable database, never a real one
    monkeypatch.setenv("TRITONSPEND_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    migrated = inspect(create_engine(url))
    reference_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(reference_engine)
    reference = inspect(reference_engine)

    assert len(FOOD_TABLES) == 14
    for table in FOOD_TABLES:
        assert _shape(migrated, table.name) == _shape(reference, table.name), table.name

    command.downgrade(config, "20261029_0004")  # removes 0008, 0007, 0006 and 0005
    remaining = set(inspect(create_engine(url)).get_table_names())
    assert not {t.name for t in FOOD_TABLES} & remaining and {"participants", "user_accounts"} <= remaining
