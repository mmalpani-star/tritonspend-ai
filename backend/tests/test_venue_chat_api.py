"""Food Chat: venue star ratings and per-venue group chat (the 2026-11-08 design)."""

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from backend.app.food_models import FoodChatMessage, FoodMenuItem, FoodReport, FoodVenue, FoodVenueRating
from backend.app.food_rate_limit import food_chat_limiter
from backend.app.main import app
from backend.app.models import UserAccount
from backend.tests.test_food_chat_api import API, MODERATOR, Student, factory, public, public_get, students  # noqa: F401

PIZZA = "I tried the Slice at Pines pepperoni pizza. The crust was great, but it was a little overpriced."


def rate(student, venue, stars, expect=200):
    return student.send("PUT", f"/venues/{venue}/rating", {"rating": stars}, expect).json()


def say(student, venue, body, expect=201):
    return student.send("POST", f"/venues/{venue}/messages", {"body": body}, expect).json()


# Ratings --------------------------------------------------------------------------------------

def test_ratings_one_per_student_changeable_with_an_exact_average(factory, students):
    alice, bob, carol = students
    assert public_get("/venues/pines/rating") == {"venue_id": "pines", "average_rating": None, "rating_count": 0, "my_rating": None}
    assert rate(alice, "pines", 5) == {"venue_id": "pines", "average_rating": 5.0, "rating_count": 1, "my_rating": 5}
    rate(bob, "pines", 4)
    summary = rate(carol, "pines", 4)
    assert (summary["average_rating"], summary["rating_count"]) == (4.33, 3)  # (5+4+4)/3, fractional
    # Changing a rating replaces it: each student still counts exactly once.
    assert rate(alice, "pines", 1)["rating_count"] == 3
    assert public_get("/venues/pines/rating")["average_rating"] == 3.0  # (1+4+4)/3
    assert alice.get("/venues/pines/rating")["my_rating"] == 1 and public_get("/venues/pines/rating")["my_rating"] is None
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodVenueRating).where(FoodVenueRating.venue_id == "pines")) == 3
    # Venues are independent; the venue list and detail use the same numbers.
    assert public_get("/venues/64-degrees/rating")["rating_count"] == 0
    assert public_get("/venues/pines")["rating"] == {"review_count": 3, "average_rating": 3.0}
    # Clearing removes only your own rating.
    cleared = alice.send("DELETE", "/venues/pines/rating", None, 200).json()
    assert (cleared["rating_count"], cleared["average_rating"], cleared["my_rating"]) == (2, 4.0, None)


def test_ratings_are_validated_and_need_session_csrf_consent_and_an_active_venue(factory, students):
    alice = students[0]
    for bad in (0, 6, 4.5, "5", None):
        alice.send("PUT", "/venues/pines/rating", {"rating": bad}, 422)
    assert public.put(API + "/venues/pines/rating", json={"rating": 4}).status_code == 401
    assert alice.client.put(API + "/venues/pines/rating", json={"rating": 4}).status_code == 403  # no CSRF header
    rate(alice, "nowhere", 4, expect=404)
    with factory() as session:
        session.get(FoodVenue, "bistro").is_active = False
        session.commit()
    rate(alice, "bistro", 4, expect=404)
    assert alice.client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": alice.token}).status_code == 200
    rate(alice, "pines", 4, expect=403)


def test_ratings_and_messages_are_independent(factory, students):
    alice, _, _ = students
    say(alice, "pines", "No rating attached to this.")
    assert public_get("/venues/pines/rating")["rating_count"] == 0
    rate(alice, "pines", 2)
    assert len(public_get("/venues/pines/messages")["messages"]) == 1


# Chat -----------------------------------------------------------------------------------------

def test_chat_is_flat_chronological_per_venue_and_mentions_any_dish(factory, students):
    alice, bob, _ = students
    sent = say(alice, "pines", PIZZA)
    assert (sent["body"], sent["is_mine"], sent["edited"]) == (PIZZA, True, False)
    say(bob, "pines", "The Margherita at Slice is cheaper.")
    say(bob, "64-degrees", "Different venue, different chat.")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodMenuItem)) == 0  # nothing added to the menu
    feed = public_get("/venues/pines/messages")
    assert [m["body"] for m in feed["messages"]] == [PIZZA, "The Margherita at Slice is cheaper."]  # oldest first
    assert feed["has_older"] is False
    assert {m["author_name"] for m in feed["messages"]} == {sent["author_name"], feed["messages"][1]["author_name"]}
    assert all(m["moderation_state"] is None and not m["is_mine"] for m in feed["messages"])  # public view
    assert [m["body"] for m in public_get("/venues/64-degrees/messages")["messages"]] == ["Different venue, different chat."]
    for bad in ("", "   ", "x" * 1001):
        say(alice, "pines", bad, expect=422)
    say(alice, "nowhere", "hi", expect=404)


def test_loading_older_messages_and_polling_for_new_ones(factory, students, monkeypatch):
    monkeypatch.setitem(food_chat_limiter.limits, "message", (1000, 60))
    alice, bob, _ = students
    for number in range(1, 8):
        say(alice if number % 2 else bob, "pines", f"message {number}")
    latest = public_get("/venues/pines/messages", limit=3)
    assert ([m["body"] for m in latest["messages"]], latest["has_older"]) == (["message 5", "message 6", "message 7"], True)
    older = public_get("/venues/pines/messages", limit=3, before=latest["messages"][0]["id"])
    assert ([m["body"] for m in older["messages"]], older["has_older"]) == (["message 2", "message 3", "message 4"], True)
    oldest = public_get("/venues/pines/messages", limit=3, before=older["messages"][0]["id"])
    assert ([m["body"] for m in oldest["messages"]], oldest["has_older"]) == (["message 1"], False)
    say(bob, "pines", "message 8")  # a poll of the newest page sees it
    assert public_get("/venues/pines/messages", limit=3)["messages"][-1]["body"] == "message 8"
    assert public.get(API + "/venues/64-degrees/messages", params={"before": latest["messages"][0]["id"]}).status_code == 404


def test_edit_and_delete_only_your_own_messages(factory, students):
    alice, bob, _ = students
    mine = say(alice, "pines", "Typo in thsi")
    edited = alice.send("PATCH", f"/messages/{mine['id']}", {"body": "Typo in this"}, 200).json()
    assert (edited["body"], edited["edited"]) == ("Typo in this", True)
    bob.send("PATCH", f"/messages/{mine['id']}", {"body": "hijack"}, 404)
    bob.send("DELETE", f"/messages/{mine['id']}", None, 404)
    alice.send("DELETE", f"/messages/{mine['id']}", None, 204)
    assert public_get("/venues/pines/messages")["messages"] == []
    alice.send("DELETE", f"/messages/{mine['id']}", None, 404)


def test_reporting_and_moderating_messages(factory, students):
    alice, bob, moderator = students
    rude = say(bob, "pines", "Something rude")
    alice.send("POST", "/reports", {"message_id": rude["id"], "reason": "harassment", "details": "not nice"}, 201)
    alice.send("POST", "/reports", {"message_id": rude["id"], "reason": "spam"}, 409)  # once per reporter
    bob.send("POST", "/reports", {"message_id": rude["id"], "reason": "spam"}, 422)  # not your own
    alice.send("POST", "/reports", {"message_id": rude["id"], "review_id": "x", "reason": "spam"}, 422)  # exactly one target
    alice.send("GET", "/moderation/reports", None, 403)

    [report] = moderator.get("/moderation/reports")["reports"]
    assert (report["content"]["kind"], report["content"]["body"], report["content"]["venue"]["id"], report["content"]["review_id"]) == (
        "message", "Something rude", "pines", None)
    moderator.send("POST", f"/moderation/messages/{rude['id']}", {"action": "hide", "note": "harassment"}, 200)
    assert public_get("/venues/pines/messages")["messages"] == []
    own_view = bob.get("/venues/pines/messages")["messages"]
    assert [(m["body"], m["moderation_state"]) for m in own_view] == [("Something rude", "hidden")]  # the author still sees it
    bob.send("PATCH", f"/messages/{rude['id']}", {"body": "edited"}, 409)
    moderator.send("POST", f"/moderation/reports/{report['id']}", {"action": "resolve"}, 200)
    actions = moderator.get("/moderation/actions")["actions"]
    assert [(a["action"], a["target_type"]) for a in actions][:2] == [("resolve_report", "report"), ("hide", "message")]
    moderator.send("POST", f"/moderation/messages/{rude['id']}", {"action": "restore"}, 200)
    assert len(public_get("/venues/pines/messages")["messages"]) == 1
    # Deleting a reported message also deletes the reports on it.
    bob.send("DELETE", f"/messages/{rude['id']}", None, 204)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodReport)) == 0


def test_chat_needs_session_csrf_and_consent_and_is_rate_limited(factory, students, monkeypatch):
    alice = students[0]
    assert public.post(API + "/venues/pines/messages", json={"body": "hi"}).status_code == 401
    assert alice.client.post(API + "/venues/pines/messages", json={"body": "hi"}).status_code == 403
    monkeypatch.setitem(food_chat_limiter.limits, "message", (2, 60))
    say(alice, "pines", "one")
    say(alice, "pines", "two")
    limited = alice.send("POST", "/venues/pines/messages", {"body": "three"}, 429)
    assert limited.headers.get("Retry-After")
    assert alice.client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": alice.token}).status_code == 200
    food_chat_limiter.reset()
    say(alice, "pines", "four", expect=403)
    assert len(public_get("/venues/pines/messages")["messages"]) == 2  # reading needs nothing


def test_responses_never_include_emails_or_participant_ids(factory, students):
    alice, bob, moderator = students
    message = say(bob, "pines", "hello")
    rate(bob, "pines", 3)
    alice.send("POST", "/reports", {"message_id": message["id"], "reason": "spam"}, 201)
    with factory() as session:
        participant_ids = set(session.scalars(select(UserAccount.participant_id)))
    bodies = [
        public.get(f"{API}/venues/pines/messages").text, bob.client.get(f"{API}/venues/pines/messages").text,
        public.get(f"{API}/venues/pines/rating").text, moderator.client.get(f"{API}/moderation/reports").text,
        bob.client.get("/api/v1/me/ratings").text, bob.client.get("/api/v1/me/messages").text,
    ]
    for body in bodies:
        assert "@example.com" not in body.lower()
        assert not any(pid in body for pid in participant_ids)


def test_your_ratings_and_messages_pages(factory, students):
    alice, bob, _ = students
    rate(alice, "pines", 4)
    rate(bob, "pines", 2)
    rate(alice, "64-degrees", 5)
    say(alice, "pines", "first")
    say(alice, "64-degrees", "second")
    say(bob, "pines", "not mine")
    ratings = alice.client.get("/api/v1/me/ratings").json()["ratings"]
    assert sorted((r["venue"]["id"], r["rating"], r["venue_average"], r["venue_rating_count"]) for r in ratings) == [
        ("64-degrees", 5, 5.0, 1), ("pines", 4, 3.0, 2)]
    messages = alice.client.get("/api/v1/me/messages").json()
    assert ([m["body"] for m in messages["messages"]], messages["total"]) == (["second", "first"], 2)
    assert messages["messages"][0]["venue"] == {"id": "64-degrees", "name": "64 Degrees"}


def test_export_and_account_deletion_cover_ratings_and_messages(factory, students):
    alice, bob, _ = students
    rate(alice, "pines", 5)
    rate(bob, "pines", 3)
    mine = say(alice, "pines", "Alice's message")
    bobs = say(bob, "pines", "Bob's message")
    bob.send("POST", "/reports", {"message_id": mine["id"], "reason": "spam"}, 201)  # a report on Alice's message
    alice.send("POST", "/reports", {"message_id": bobs["id"], "reason": "spam"}, 201)  # a report Alice made

    exported = alice.client.get("/api/v1/pilot/export").json()
    assert exported["schema_version"] == "stage8.v1"
    assert [(r["venue_id"], r["rating"]) for r in exported["food_chat"]["venue_ratings"]] == [("pines", 5)]
    assert [m["body"] for m in exported["food_chat"]["chat_messages"]] == ["Alice's message"]
    assert [r["message_id"] for r in exported["food_chat"]["reports"]] == [bobs["id"]]

    assert alice.client.request("DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"},
                                headers={"X-CSRF-Token": alice.token}).status_code == 200
    assert [m["body"] for m in public_get("/venues/pines/messages")["messages"]] == ["Bob's message"]
    assert public_get("/venues/pines/rating") == {"venue_id": "pines", "average_rating": 3.0, "rating_count": 1, "my_rating": None}
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodReport)) == 0  # both reports involved Alice
        assert session.scalar(select(func.count()).select_from(FoodChatMessage)) == 1
        assert session.scalar(select(func.count()).select_from(FoodVenueRating)) == 1


# Migration ------------------------------------------------------------------------------------

def test_migration_backfills_visible_venue_review_ratings_only_and_keeps_old_records(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'transition.db'}"  # disposable database, never a real one
    monkeypatch.setenv("TRITONSPEND_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "20261107_0007")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO participants (id, created_at, timezone) VALUES ('p1', '2026-11-01', 'UTC'), ('p2', '2026-11-01', 'UTC')"))
        connection.execute(text(
            "INSERT INTO food_venues (id, name, operator, kind, tags, on_campus, dining_dollars_acceptance, dining_dollars_reason, "
            "triton_cash_acceptance, triton_cash_reason, sources, notes, catalog_version, verified_on) VALUES "
            "('v1', 'Venue One', 'hdh', 'restaurant', '[]', 1, 'accepted', 'test', 'accepted', 'test', '[]', '[]', 'test', '2026-11-01')"
        ))
        connection.execute(text("INSERT INTO food_stations (id, venue_id, name, sources, catalog_version, verified_on) VALUES ('s1', 'v1', 'Grill', '[]', 'test', '2026-11-01')"))
        connection.execute(text("INSERT INTO food_menu_items (id, station_id, name, name_key, source_url, verified_at) VALUES ('m1', 's1', 'Bowl', 'bowl', 'https://example.test', '2026-11-01')"))
        connection.execute(text(
            "INSERT INTO food_reviews (id, participant_id, target_type, venue_id, station_id, menu_item_id, rating, body, moderation_state, created_at, updated_at) VALUES "
            "('r1', 'p1', 'venue', 'v1', NULL, NULL, 4, 'visible venue review', 'visible', '2026-11-02', '2026-11-03'), "
            "('r2', 'p2', 'venue', 'v1', NULL, NULL, 1, 'hidden venue review', 'hidden', '2026-11-02', '2026-11-02'), "
            "('r3', 'p2', 'menu_item', 'v1', 's1', 'm1', 5, 'dish review', 'visible', '2026-11-02', '2026-11-02')"
        ))
        connection.execute(text("INSERT INTO food_comments (id, review_id, participant_id, body, moderation_state, created_at, updated_at) VALUES ('c1', 'r1', 'p2', 'old comment', 'visible', '2026-11-02', '2026-11-02')"))
        connection.execute(text("INSERT INTO food_reports (id, participant_id, review_id, reason, status, created_at) VALUES ('rep1', 'p2', 'r1', 'spam', 'open', '2026-11-02')"))
        connection.execute(text("INSERT INTO food_moderation_actions (id, moderator_participant_id, action, target_type, target_id, created_at) VALUES ('a1', 'p1', 'hide', 'review', 'r2', '2026-11-02')"))
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        ratings = connection.execute(text("SELECT participant_id, venue_id, rating FROM food_venue_ratings")).all()
        assert ratings == [("p1", "v1", 4)]  # hidden and dish review ratings are not venue ratings
        assert connection.execute(text("SELECT count(*) FROM food_reviews")).scalar() == 3
        assert connection.execute(text("SELECT body FROM food_comments")).scalar() == "old comment"
        assert connection.execute(text("SELECT id, review_id, message_id FROM food_reports")).all() == [("rep1", "r1", None)]
        assert connection.execute(text("SELECT target_type FROM food_moderation_actions")).scalar() == "review"
        assert connection.execute(text("SELECT count(*) FROM food_chat_messages")).scalar() == 0  # nothing fabricated
        assert connection.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    engine.dispose()
    command.downgrade(config, "20261107_0007")
    with create_engine(url).connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM food_reviews")).scalar() == 3
        assert connection.execute(text("SELECT count(*) FROM food_reports")).scalar() == 1
