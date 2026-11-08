"""Food Chat API: reviews, comments, votes, reports, moderation, privacy and account deletion."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.app import db
from backend.app.config import Settings, get_settings
from backend.app.db import Base, get_db
from backend.app.food_catalog import seed_food_catalog
from backend.app.food_models import FoodChatProfile, FoodComment, FoodMenuItem, FoodModerationAction, FoodReview, FoodVenue
from backend.app.food_rate_limit import food_chat_limiter
from backend.app.main import app
from backend.app.models import UserAccount
from backend.tests.test_accounts import accept_consent, signup
from backend.tests.test_food_api import add_item
from backend.tests.test_food_catalog import sqlite_engine

API = "/api/v1/food"
MODERATOR = "Mod@Example.com"  # matched case-insensitively


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
        food_moderator_emails=("mod@example.com",),
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
    food_chat_limiter.reset()
    yield session_factory
    food_chat_limiter.reset()
    app.dependency_overrides.clear()


class Student:
    def __init__(self, email):
        self.client = TestClient(app)
        assert signup(self.client, email=email, password="correct horse battery").status_code == 201
        self.token = accept_consent(self.client)
        self.email = email

    def send(self, method, path, body=None, expect=None):
        response = self.client.request(method, API + path, json=body, headers={"X-CSRF-Token": self.token})
        if expect is not None:
            assert response.status_code == expect, response.text
        return response

    def get(self, path, **params):
        response = self.client.get(API + path, params=params)
        assert response.status_code == 200, response.text
        return response.json()


public = TestClient(app)


def public_get(path, **params):
    response = public.get(API + path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def venue_review(student, venue="pines", rating=4, body="Solid pizza", expect=201):
    response = student.send("POST", "/reviews", {"target_type": "venue", "venue_id": venue, "rating": rating, "body": body}, expect)
    return response.json()


def comment(student, review_id, body="Agreed", parent_id=None, expect=201):
    return student.send("POST", f"/reviews/{review_id}/comments", {"body": body, "parent_id": parent_id}, expect).json()


@pytest.fixture
def students(factory):
    return Student("alice@example.com"), Student("bob@example.com"), Student(MODERATOR)


# Reviews ---------------------------------------------------------------------------------------

def test_venue_review_lifecycle_with_ratings_and_pseudonyms(factory, students):
    alice, bob, _ = students
    created = venue_review(alice, rating=4, body="  Solid pizza  ")
    assert (created["rating"], created["body"], created["is_mine"], created["edited"]) == (4, "Solid pizza", True, False)
    assert re.fullmatch(r"[A-Z][a-z]+ [A-Za-z ]+ \d{4}", created["author_name"])
    venue_review(bob, rating=1, body="Too salty")

    listing = public_get("/venues/pines/reviews")
    assert listing["summary"] == {"review_count": 2, "average_rating": 2.5, "breakdown": {"1": 1, "2": 0, "3": 0, "4": 1, "5": 0}}
    assert [r["body"] for r in listing["reviews"]] == ["Too salty", "Solid pizza"]  # newest first
    assert [r["rating"] for r in public_get("/venues/pines/reviews", sort="highest")["reviews"]] == [4, 1]
    assert [r["rating"] for r in public_get("/venues/pines/reviews", sort="lowest")["reviews"]] == [1, 4]
    assert listing["my_review"] is None and not any(r["is_mine"] for r in listing["reviews"])
    assert alice.get("/venues/pines/reviews")["my_review"]["id"] == created["id"]
    assert public_get("/venues/64-degrees/reviews")["summary"] == {"review_count": 0, "average_rating": None, "breakdown": {str(s): 0 for s in range(1, 6)}}

    # One review per student per venue; edit instead.
    assert venue_review(alice, rating=5, expect=409)["detail"].startswith("You've already reviewed this")
    edited = alice.send("PATCH", f"/reviews/{created['id']}", {"rating": 5, "body": "Even better now"}, 200).json()
    assert (edited["rating"], edited["body"], edited["edited"]) == (5, "Even better now", True)
    bob.send("PATCH", f"/reviews/{created['id']}", {"rating": 1}, 404)  # not the owner
    bob.send("DELETE", f"/reviews/{created['id']}", expect=404)
    assert public_get("/venues/pines/reviews")["summary"]["average_rating"] == 3.0

    alice.send("DELETE", f"/reviews/{created['id']}", expect=204)
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 1
    venue_review(alice, rating=3)  # can review again after deleting


@pytest.mark.parametrize("body, status", [
    ({"target_type": "venue", "venue_id": "pines", "rating": 0, "body": "x"}, 422),
    ({"target_type": "venue", "venue_id": "pines", "rating": 6, "body": "x"}, 422),
    ({"target_type": "venue", "venue_id": "pines", "rating": 4.5, "body": "x"}, 422),
    ({"target_type": "venue", "venue_id": "pines", "rating": 4, "body": "   "}, 422),
    ({"target_type": "venue", "venue_id": "pines", "rating": 4, "body": "x" * 2001}, 422),
    ({"target_type": "venue", "venue_id": "pines", "station_id": "pines--char", "rating": 4, "body": "x"}, 422),
    ({"target_type": "menu_item", "venue_id": "pines", "rating": 4, "body": "x"}, 422),
    ({"target_type": "venue", "venue_id": "nowhere", "rating": 4, "body": "x"}, 404),
    ({"target_type": "venue", "venue_id": "pines", "rating": 4, "body": "x", "author": "me"}, 422),
])
def test_review_input_is_validated(factory, students, body, status):
    students[0].send("POST", "/reviews", body, status)


def test_reviews_need_a_session_csrf_and_active_consent(factory, students):
    alice = students[0]
    body = {"target_type": "venue", "venue_id": "pines", "rating": 4, "body": "x"}
    assert public.post(API + "/reviews", json=body).status_code == 401
    assert alice.client.post(API + "/reviews", json=body).status_code == 403  # no CSRF header
    alice.send("POST", "/reviews", body, 201)
    assert alice.client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": alice.token}).status_code == 200
    alice.send("POST", "/reviews", {**body, "venue_id": "bistro"}, 403)


def test_inactive_venues_take_no_new_reviews(factory, students):
    with factory() as session:
        session.get(FoodVenue, "bistro").is_active = False
        session.commit()
    venue_review(students[0], venue="bistro", expect=404)


def test_dish_reviews_need_a_real_item_at_that_station_and_venue(factory, students):
    alice, bob, _ = students
    item = add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl")
    dish = {"target_type": "menu_item", "venue_id": "64-degrees", "station_id": "64-degrees--triton-grill", "menu_item_id": item, "rating": 5, "body": "Great bowl"}
    alice.send("POST", "/reviews", {**dish, "venue_id": "pines"}, 422)  # station is not at Pines
    alice.send("POST", "/reviews", {**dish, "station_id": "64-degrees--al-dente"}, 422)  # item is not at Al Dente
    alice.send("POST", "/reviews", {**dish, "menu_item_id": "missing"}, 422)
    created = alice.send("POST", "/reviews", dish, 201).json()
    assert (created["station"], created["menu_item"]) == ({"id": "64-degrees--triton-grill", "name": "Triton Grill"}, {"id": item, "name": "Chicken Rice Bowl"})
    alice.send("POST", "/reviews", dish, 409)
    bob.send("POST", "/reviews", {**dish, "rating": 2, "body": "Dry"}, 201)
    venue_review(alice, venue="64-degrees", rating=1)  # a venue review is a separate target

    detail = public_get(f"/menu-items/{item}")
    assert (detail["station"]["name"], detail["venue"]["name"], detail["rating"]["review_count"], detail["rating"]["average_rating"]) == ("Triton Grill", "64 Degrees", 2, 3.5)
    assert public_get(f"/menu-items/{item}/reviews")["summary"]["review_count"] == 2
    assert public_get("/venues/64-degrees/reviews")["summary"]["review_count"] == 1  # dish reviews don't count
    menu = public_get("/stations/64-degrees--triton-grill/menu-items")
    assert menu["items"][0]["rating"] == {"review_count": 2, "average_rating": 3.5}


# Comments ---------------------------------------------------------------------------------------

def test_threaded_comments_replies_edits_and_deletion(factory, students):
    alice, bob, _ = students
    review = venue_review(alice)
    other_review = venue_review(bob, venue="bistro")
    top = comment(bob, review["id"], "Which slice?")
    reply = comment(alice, review["id"], "Pepperoni", parent_id=top["id"])
    comment(bob, review["id"], "Nice", parent_id=reply["id"])
    comment(alice, other_review["id"], "Wrong thread", parent_id=top["id"], expect=422)
    comment(alice, review["id"], "", expect=422)
    comment(alice, review["id"], "x" * 1001, expect=422)

    listing = public_get(f"/reviews/{review['id']}/comments", sort="oldest")
    assert [(c["body"], c["parent_id"]) for c in listing["comments"]] == [("Which slice?", None), ("Pepperoni", top["id"]), ("Nice", reply["id"])]
    assert public_get("/venues/pines/reviews")["reviews"][0]["comment_count"] == 3

    alice.send("PATCH", f"/comments/{reply['id']}", {"body": "Pepperoni, obviously"}, 200)
    bob.send("PATCH", f"/comments/{reply['id']}", {"body": "hijack"}, 404)
    edited = {c["id"]: c for c in public_get(f"/reviews/{review['id']}/comments")["comments"]}[reply["id"]]
    assert (edited["body"], edited["edited"]) == ("Pepperoni, obviously", True)

    alice.send("DELETE", f"/comments/{reply['id']}", expect=204)  # Bob's reply survives, moved up
    after = public_get(f"/reviews/{review['id']}/comments", sort="oldest")["comments"]
    assert [(c["body"], c["parent_id"]) for c in after] == [("Which slice?", None), ("Nice", top["id"])]

    alice.send("DELETE", f"/reviews/{review['id']}", expect=204)  # the whole discussion goes with the review
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodComment).where(FoodComment.review_id == review["id"])) == 0
    assert public.get(f"{API}/reviews/{review['id']}/comments").status_code == 404


def test_reply_depth_is_limited(factory, students):
    alice, bob, _ = students
    review = venue_review(alice)
    parent = None
    for depth in range(8):
        parent = comment(bob if depth % 2 else alice, review["id"], f"level {depth + 1}", parent_id=parent and parent["id"])
    comment(alice, review["id"], "too deep", parent_id=parent["id"], expect=422)


# Votes ------------------------------------------------------------------------------------------

def test_one_vote_per_student_which_can_change_or_be_removed(factory, students):
    alice, bob, moderator = students
    review = venue_review(alice)
    target = comment(alice, review["id"], "Vote on me")
    assert bob.send("PUT", f"/comments/{target['id']}/vote", {"value": 1}, 200).json() == {"comment_id": target["id"], "score": 1, "upvotes": 1, "downvotes": 0, "my_vote": 1}
    assert bob.send("PUT", f"/comments/{target['id']}/vote", {"value": 1}, 200).json()["score"] == 1  # still one vote
    assert moderator.send("PUT", f"/comments/{target['id']}/vote", {"value": -1}, 200).json()["score"] == 0
    assert bob.send("PUT", f"/comments/{target['id']}/vote", {"value": -1}, 200).json() == {"comment_id": target["id"], "score": -2, "upvotes": 0, "downvotes": 2, "my_vote": -1}
    assert bob.send("DELETE", f"/comments/{target['id']}/vote", expect=200).json()["my_vote"] == 0
    bob.send("PUT", f"/comments/{target['id']}/vote", {"value": 2}, 422)
    alice.send("PUT", f"/comments/{target['id']}/vote", {"value": 1}, 422)  # not on your own comment
    assert {c["id"]: c for c in moderator.get(f"/reviews/{review['id']}/comments")["comments"]}[target["id"]]["my_vote"] == -1
    assert public_get(f"/reviews/{review['id']}/comments")["comments"][0]["my_vote"] == 0


def test_top_sort_orders_comments_by_score(factory, students):
    alice, bob, moderator = students
    review = venue_review(alice)
    low, high = comment(alice, review["id"], "low"), comment(alice, review["id"], "high")
    for voter in (bob, moderator):
        voter.send("PUT", f"/comments/{high['id']}/vote", {"value": 1}, 200)
    bob.send("PUT", f"/comments/{low['id']}/vote", {"value": -1}, 200)
    assert [c["body"] for c in public_get(f"/reviews/{review['id']}/comments", sort="top")["comments"]] == ["high", "low"]
    assert [c["body"] for c in public_get(f"/reviews/{review['id']}/comments", sort="newest")["comments"]] == ["high", "low"]


# Reports and moderation -----------------------------------------------------------------------

def test_reports_are_validated(factory, students):
    alice, bob, _ = students
    review = venue_review(alice)
    note = comment(alice, review["id"], "hello")
    assert bob.send("POST", "/reports", {"review_id": review["id"], "reason": "spam"}, 201).json()["status"] == "open"
    bob.send("POST", "/reports", {"review_id": review["id"], "reason": "hate"}, 409)
    bob.send("POST", "/reports", {"comment_id": note["id"], "reason": "harassment", "details": "rude"}, 201)
    alice.send("POST", "/reports", {"review_id": review["id"], "reason": "spam"}, 422)  # own post
    bob.send("POST", "/reports", {"review_id": review["id"], "comment_id": note["id"], "reason": "spam"}, 422)
    bob.send("POST", "/reports", {"reason": "spam"}, 422)
    bob.send("POST", "/reports", {"comment_id": note["id"], "reason": "made-up"}, 422)
    bob.send("POST", "/reports", {"comment_id": "missing", "reason": "spam"}, 404)


def test_only_configured_moderators_can_moderate(factory, students):
    alice, bob, moderator = students
    review = venue_review(alice)
    for student in (alice, bob):
        assert student.client.get(f"{API}/moderation/reports").status_code == 403
        student.send("POST", f"/moderation/reviews/{review['id']}", {"action": "hide"}, 403)
    assert public.get(f"{API}/moderation/reports").status_code == 401
    assert alice.get("/me") == {"display_name": review["author_name"], "is_moderator": False, "consent_active": True}
    assert moderator.get("/me")["is_moderator"] is True
    assert public.get(f"{API}/me").status_code == 401


def test_moderators_hide_restore_remove_and_resolve(factory, students):
    alice, bob, moderator = students
    review = venue_review(alice, body="Spammy")
    top = comment(bob, review["id"], "first")
    hidden_comment = comment(alice, review["id"], "rude reply", parent_id=top["id"])
    comment(bob, review["id"], "reply under the rude one", parent_id=hidden_comment["id"])
    report = bob.send("POST", "/reports", {"review_id": review["id"], "reason": "spam", "details": "ads"}, 201).json()
    bob.send("POST", "/reports", {"comment_id": hidden_comment["id"], "reason": "harassment"}, 201)

    queue = moderator.get("/moderation/reports")
    assert queue["total"] == 2
    first = queue["reports"][0]
    assert (first["reason"], first["details"], first["content"]["kind"], first["content"]["body"], first["content"]["venue"]["name"]) == ("spam", "ads", "review", "Spammy", "Pines")
    assert first["content"]["author_name"] == review["author_name"]

    # Hiding a comment with a visible reply leaves an empty placeholder in its place.
    moderator.send("POST", f"/moderation/comments/{hidden_comment['id']}", {"action": "hide", "note": "harassment"}, 200)
    listed = {c["id"]: c for c in public_get(f"/reviews/{review['id']}/comments")["comments"]}
    assert listed[hidden_comment["id"]] | {"created_at": None} == {
        "id": hidden_comment["id"], "parent_id": top["id"], "is_placeholder": True, "body": None, "author_name": None,
        "is_mine": False, "score": 0, "upvotes": 0, "downvotes": 0, "my_vote": 0, "edited": False, "created_at": None,
    }
    comment(alice, review["id"], "reply to hidden", parent_id=hidden_comment["id"], expect=422)
    alice.send("PATCH", f"/comments/{hidden_comment['id']}", {"body": "sorry"}, 409)

    moderator.send("POST", f"/moderation/reviews/{review['id']}", {"action": "hide"}, 200)
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 0
    assert public.get(f"{API}/reviews/{review['id']}").status_code == 404
    assert alice.get(f"/reviews/{review['id']}")["moderation_state"] == "hidden"  # the author still sees it
    assert alice.get("/venues/pines/reviews")["my_review"]["moderation_state"] == "hidden"
    assert moderator.get(f"/reviews/{review['id']}")["moderation_state"] == "hidden"
    bob.send("POST", f"/reviews/{review['id']}/comments", {"body": "hi"}, 404)

    moderator.send("POST", f"/moderation/reviews/{review['id']}", {"action": "restore"}, 200)
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 1
    moderator.send("POST", f"/moderation/reviews/{review['id']}", {"action": "remove"}, 200)
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 0
    moderator.send("POST", f"/moderation/reviews/{review['id']}", {"action": "delete"}, 422)

    assert moderator.send("POST", f"/moderation/reports/{report['id']}", {"action": "resolve"}, 200).json()["status"] == "actioned"
    remaining = moderator.get("/moderation/reports")["reports"]
    moderator.send("POST", f"/moderation/reports/{remaining[0]['id']}", {"action": "dismiss"}, 200)
    assert moderator.get("/moderation/reports")["total"] == 0
    assert moderator.get("/moderation/reports", status="all")["total"] == 2

    history = moderator.get("/moderation/actions")["actions"]
    assert [a["action"] for a in history][::-1] == ["hide", "hide", "restore", "remove", "resolve_report", "dismiss_report"]
    assert history[-1]["note"] == "harassment"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodModerationAction)) == 6


def test_write_limits_answer_429(factory, students, monkeypatch):
    alice, bob, _ = students
    review = venue_review(alice)
    monkeypatch.setitem(food_chat_limiter.limits, "comment", (2, 600))
    comment(bob, review["id"], "one")
    comment(bob, review["id"], "two")
    response = bob.send("POST", f"/reviews/{review['id']}/comments", {"body": "three"})
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    comment(alice, review["id"], "others are unaffected")


# Privacy, export and account deletion ---------------------------------------------------------

def test_responses_never_include_emails_or_participant_ids(factory, students):
    alice, bob, moderator = students
    review = venue_review(alice)
    note = comment(bob, review["id"], "hi")
    bob.send("POST", "/reports", {"review_id": review["id"], "reason": "spam"}, 201)
    with factory() as session:
        participant_ids = set(session.scalars(select(UserAccount.participant_id)))
    bodies = [
        public.get(f"{API}/venues/pines/reviews").text, alice.client.get(f"{API}/venues/pines/reviews").text,
        public.get(f"{API}/reviews/{review['id']}/comments").text, public.get(f"{API}/reviews/{review['id']}").text,
        moderator.client.get(f"{API}/moderation/reports").text, moderator.client.get(f"{API}/moderation/actions").text,
        alice.client.get(f"{API}/me").text, bob.send("PATCH", f"/comments/{note['id']}", {"body": "hello"}).text,
    ]
    for body in bodies:
        assert "@example.com" not in body.lower()
        assert not any(pid in body for pid in participant_ids)


def test_export_and_account_deletion_follow_the_policy(factory, students):
    alice, bob, _ = students
    alice_review = venue_review(alice)
    bob_review = venue_review(bob, venue="bistro")
    question = comment(bob, bob_review["id"], "Bob asks")
    answer = comment(alice, bob_review["id"], "Alice answers", parent_id=question["id"])
    comment(bob, bob_review["id"], "Bob follows up", parent_id=answer["id"])
    comment(bob, alice_review["id"], "On Alice's review")
    alice.send("PUT", f"/comments/{question['id']}/vote", {"value": 1}, 200)
    alice.send("POST", "/reports", {"review_id": bob_review["id"], "reason": "off_topic"}, 201)

    exported = alice.client.get("/api/v1/pilot/export").json()["food_chat"]
    assert exported["display_name"] == alice_review["author_name"]
    assert (len(exported["reviews"]), len(exported["comments"]), len(exported["comment_votes"]), len(exported["reports"])) == (1, 1, 1, 1)

    assert alice.client.request("DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"},
                                headers={"X-CSRF-Token": alice.token}).status_code == 200
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 0
    thread = public_get(f"/reviews/{bob_review['id']}/comments", sort="oldest")["comments"]
    assert [(c["body"], c["parent_id"]) for c in thread] == [("Bob asks", None), ("Bob follows up", question["id"])]
    assert thread[0]["score"] == 0  # Alice's vote is gone
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodChatProfile)) == 1  # only Bob's pseudonym is left
        assert session.scalar(select(func.count()).select_from(FoodReview)) == 1


# Venue-only Food Chat (2026-11-07): pick a venue, mention any dish in your own words -----------

def test_a_review_needs_only_a_venue_and_can_mention_any_dish(factory, students):
    alice, bob, moderator = students
    text = "I tried the Slice at Pines pepperoni pizza. The crust was great, but it was a little overpriced."
    # No target_type, station or menu item: the venue is enough, and no menu data exists for this dish.
    created = alice.send("POST", "/reviews", {"venue_id": "pines", "rating": 4, "body": text}, 201).json()
    assert (created["target_type"], created["venue"], created["station"], created["menu_item"]) == ("venue", {"id": "pines", "name": "Pines"}, None, None)
    assert created["body"] == text
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodMenuItem)) == 0  # nothing was added to the menu
    listing = public_get("/venues/pines/reviews")
    assert [r["body"] for r in listing["reviews"]] == [text] and listing["summary"]["review_count"] == 1

    # Discussion: comments and replies need no station or dish either.
    question = comment(bob, created["id"], "Was the pepperoni spicy?")
    answer = comment(alice, created["id"], "A little. The Margherita at Slice is milder.", parent_id=question["id"])
    thread = public_get(f"/reviews/{created['id']}/comments", sort="oldest")["comments"]
    assert [(c["body"], c["parent_id"]) for c in thread] == [
        ("Was the pepperoni spicy?", None), ("A little. The Margherita at Slice is milder.", question["id"])]

    # Votes, reports, edits, moderation and deletion work as before.
    assert alice.send("PUT", f"/comments/{question['id']}/vote", {"value": 1}, 200).json()["score"] == 1
    bob.send("POST", "/reports", {"review_id": created["id"], "reason": "off_topic"}, 201)
    edited = alice.send("PATCH", f"/reviews/{created['id']}", {"body": text + " Still worth it."}, 200).json()
    assert edited["edited"] is True and edited["body"].endswith("Still worth it.")
    alice.send("POST", "/reviews", {"venue_id": "pines", "rating": 2, "body": "Second try"}, 409)  # still one per venue
    moderator.send("POST", f"/moderation/reviews/{created['id']}", {"action": "hide"}, 200)
    assert public_get("/venues/pines/reviews")["reviews"] == []
    moderator.send("POST", f"/moderation/reviews/{created['id']}", {"action": "restore"}, 200)
    alice.send("DELETE", f"/reviews/{created['id']}", None, 204)
    assert public_get("/venues/pines/reviews")["summary"]["review_count"] == 0


def test_existing_dish_reviews_still_load_and_can_be_edited_or_deleted(factory, students):
    alice, bob, _ = students
    item = add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl")
    old = alice.send("POST", "/reviews", {"target_type": "menu_item", "venue_id": "64-degrees", "station_id": "64-degrees--triton-grill",
                                          "menu_item_id": item, "rating": 5, "body": "Older dish review"}, 201).json()
    reply = comment(bob, old["id"], "Agreed")
    shown = public_get(f"/reviews/{old['id']}")
    assert (shown["venue"]["name"], shown["menu_item"]["name"], shown["station"]["name"]) == ("64 Degrees", "Chicken Rice Bowl", "Triton Grill")
    assert public_get(f"/reviews/{old['id']}/comments")["comments"][0]["id"] == reply["id"]
    venue_review(alice, venue="64-degrees", rating=3, body="Venue review alongside the old dish review")  # separate target
    alice.send("PATCH", f"/reviews/{old['id']}", {"rating": 4}, 200)
    alice.send("DELETE", f"/reviews/{old['id']}", None, 204)
    assert public_get("/venues/64-degrees/reviews")["summary"]["review_count"] == 1
