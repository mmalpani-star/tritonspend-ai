"""The application's SQLite engines enforce foreign keys, like PostgreSQL does.

Uses the real engine builders (create_engine_from_settings, build_session_factory, get_engine)
against a temporary database file, never the local tritonspend.db.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.app import db
from backend.app.config import Settings
from backend.app.db import Base, build_session_factory, create_engine_from_settings
from backend.app.food_catalog import menu_name_key, seed_food_catalog
from backend.app.food_models import FoodMenuItem, FoodReview, FoodStation, ReviewTarget
from backend.app.models import Participant

NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)


def settings(url):
    return Settings(database_url=url, environment="test")


@pytest.fixture
def app_session(tmp_path):
    factory = build_session_factory(settings(f"sqlite:///{tmp_path / 'app.db'}"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        seed_food_catalog(session)
        session.commit()
        yield session


def foreign_keys_enabled(connection):
    return connection.execute(text("PRAGMA foreign_keys")).scalar()


def test_every_application_sqlite_connection_has_foreign_keys_on(tmp_path, monkeypatch):
    engine = create_engine_from_settings(settings(f"sqlite:///{tmp_path / 'one.db'}"))
    first, second = engine.connect(), engine.connect()  # two pooled DBAPI connections
    assert foreign_keys_enabled(first) == foreign_keys_enabled(second) == 1
    first.close(), second.close()
    engine.dispose()
    with engine.connect() as fresh:  # a brand-new connection after the pool was emptied
        assert foreign_keys_enabled(fresh) == 1

    with build_session_factory(settings(f"sqlite:///{tmp_path / 'two.db'}"))() as session:
        assert foreign_keys_enabled(session.connection()) == 1

    # The app-wide cached engine used by request sessions.
    monkeypatch.setenv("TRITONSPEND_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'three.db'}")
    db.get_engine.cache_clear()
    try:
        with db.get_engine().connect() as connection:
            assert foreign_keys_enabled(connection) == 1
    finally:
        db.get_engine.cache_clear()


def test_postgresql_engines_are_unchanged_and_only_sqlite_gets_the_hook():
    # Built without connecting. Dialects add their own pool listeners, so compare each app engine
    # with a plain engine for the same URL: PostgreSQL gets nothing extra, SQLite exactly one hook.
    def listeners(engine):
        return len(engine.pool.dispatch.connect)  # "connect" listeners on an engine live on its pool

    postgres_url = "postgresql+psycopg://user:not-a-real-password@db.example.invalid/app"
    assert listeners(create_engine_from_settings(settings(postgres_url))) == listeners(create_engine(postgres_url))
    sqlite_url = "sqlite:///:memory:"
    assert listeners(create_engine_from_settings(settings(sqlite_url))) == listeners(create_engine(sqlite_url)) + 1


def rejected(session, record):
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with session.begin_nested():
            session.add(record)
            session.flush()


def test_station_cannot_reference_a_nonexistent_venue(app_session):
    rejected(app_session, FoodStation(id="nowhere--grill", venue_id="nowhere", name="Grill", sources=[],
                                      catalog_version="test", verified_on=date(2026, 11, 7)))


def test_menu_item_cannot_reference_a_nonexistent_station(app_session):
    rejected(app_session, FoodMenuItem(station_id="pines--no-such-station", name="Slice", name_key="slice",
                                       source_url="https://example.test/menu", verified_at=NOW))


def test_dish_review_cannot_use_a_station_from_another_venue(app_session):
    participant = Participant()
    item = FoodMenuItem(station_id="64-degrees--triton-grill", name="Chicken Rice Bowl",
                        name_key=menu_name_key("Chicken Rice Bowl"), source_url="https://example.test/menu", verified_at=NOW)
    app_session.add_all([participant, item])
    app_session.flush()
    # Triton Grill is at 64 Degrees, not Pines.
    rejected(app_session, FoodReview(participant_id=participant.id, target_type=ReviewTarget.menu_item, venue_id="pines",
                                     station_id="64-degrees--triton-grill", menu_item_id=item.id, rating=4, body=""))
    # The same review against the right venue is accepted.
    app_session.add(FoodReview(participant_id=participant.id, target_type=ReviewTarget.menu_item, venue_id="64-degrees",
                               station_id="64-degrees--triton-grill", menu_item_id=item.id, rating=4, body=""))
    app_session.flush()
