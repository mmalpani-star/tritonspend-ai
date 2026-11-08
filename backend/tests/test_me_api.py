"""The signed-in participant's private pages: account, favourites and their own activity."""

import re

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.food_models import FoodChatProfile, FoodFavoriteDish, FoodFavoriteVenue, FoodVenue
from backend.app.main import app
from backend.app.models import UserAccount
from backend.tests.test_accounts import signup
from backend.tests.test_food_api import add_item
from backend.tests.test_food_chat_api import API, Student, comment, factory, students, venue_review  # noqa: F401

ME = "/api/v1/me"


def me(student, method, path, expect=200):
    response = student.client.request(method, ME + path, headers={"X-CSRF-Token": student.token})
    assert response.status_code == expect, response.text
    return response.json() if response.content else None


# Account --------------------------------------------------------------------------------------

def test_account_shows_private_email_pseudonym_consent_and_counts(factory, students):
    alice, bob, moderator = students
    account = me(alice, "GET", "/account")
    assert account["email"] == "alice@example.com"
    assert re.fullmatch(r"[A-Z][a-z]+ [A-Za-z ]+ \d{4}", account["display_name"])
    assert (account["consent"]["active"], account["consent"]["version"], account["is_moderator"]) == (True, "v1", False)
    assert account["activity"] == {"ratings": 0, "messages": 0, "favorite_venues": 0, "favorite_dishes": 0}
    # The pseudonym is stable and is the one shown on posts.
    assert venue_review(alice)["author_name"] == account["display_name"] == me(alice, "GET", "/account")["display_name"]
    alice.send("PUT", "/venues/pines/rating", {"rating": 5}, 200)
    alice.send("POST", "/venues/pines/messages", {"body": "Hi Pines"}, 201)
    activity = me(alice, "GET", "/account")["activity"]
    assert (activity["ratings"], activity["messages"]) == (1, 1)
    assert me(moderator, "GET", "/account")["is_moderator"] is True
    assert me(bob, "GET", "/account")["email"] == "bob@example.com"  # each caller sees only their own


def test_account_without_consent_has_no_pseudonym_yet(factory):
    client = TestClient(app)
    assert signup(client, email="new@example.com", password="correct horse battery").status_code == 201
    account = client.get(ME + "/account").json()
    assert (account["email"], account["display_name"], account["consent"]["active"]) == ("new@example.com", None, False)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodChatProfile)) == 0


def test_private_pages_need_a_session(factory):
    anonymous = TestClient(app)
    for path in ("/account", "/favorites", "/reviews", "/comments"):
        assert anonymous.get(ME + path).status_code == 401, path


# Favourites -----------------------------------------------------------------------------------

def test_favourite_venues_are_saved_listed_and_removed(factory, students):
    alice, bob, _ = students
    assert me(alice, "GET", "/favorites") == {"venues": [], "dishes": []}
    assert me(alice, "PUT", "/favorites/venues/pines") == {"kind": "venue", "id": "pines", "saved": True}
    me(alice, "PUT", "/favorites/venues/pines")  # saving twice is harmless
    me(alice, "PUT", "/favorites/venues/64-degrees")
    bob.send("PUT", "/venues/pines/rating", {"rating": 4}, 200)

    saved = me(alice, "GET", "/favorites")["venues"]
    assert sorted(v["id"] for v in saved) == ["64-degrees", "pines"]
    pines = next(v for v in saved if v["id"] == "pines")
    assert (pines["name"], pines["is_active"], pines["rating"]) == ("Pines", True, {"review_count": 1, "average_rating": 4.0})
    assert me(bob, "GET", "/favorites")["venues"] == []  # private to Alice

    assert me(alice, "DELETE", "/favorites/venues/pines") == {"kind": "venue", "id": "pines", "saved": False}
    me(alice, "DELETE", "/favorites/venues/pines")  # removing twice is harmless
    assert [v["id"] for v in me(alice, "GET", "/favorites")["venues"]] == ["64-degrees"]
    me(alice, "PUT", "/favorites/venues/not-a-venue", expect=404)
    with factory() as session:
        session.get(FoodVenue, "bistro").is_active = False
        session.commit()
    me(alice, "PUT", "/favorites/venues/bistro", expect=404)


def test_favourite_dishes_need_a_real_menu_item(factory, students):
    alice, _, _ = students
    me(alice, "PUT", "/favorites/dishes/not-a-dish", expect=404)
    item = add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl")
    me(alice, "PUT", f"/favorites/dishes/{item}")
    [dish] = me(alice, "GET", "/favorites")["dishes"]
    assert (dish["id"], dish["name"], dish["station"]["name"], dish["venue"]["name"], dish["rating"]["average_rating"]) == (
        item, "Chicken Rice Bowl", "Triton Grill", "64 Degrees", None)
    me(alice, "DELETE", f"/favorites/dishes/{item}")
    assert me(alice, "GET", "/favorites")["dishes"] == []


def test_favourite_changes_need_csrf_and_consent(factory, students):
    alice = students[0]
    assert TestClient(app).put(ME + "/favorites/venues/pines").status_code == 401
    assert alice.client.put(ME + "/favorites/venues/pines").status_code == 403  # no CSRF header
    assert alice.client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": alice.token}).status_code == 200
    me(alice, "PUT", "/favorites/venues/pines", expect=403)
    assert me(alice, "GET", "/favorites") == {"venues": [], "dishes": []}  # still readable


# Your activity --------------------------------------------------------------------------------

def test_your_reviews_include_venue_and_dish_reviews_and_moderation_state(factory, students):
    alice, bob, moderator = students
    item = add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl")
    venue_review(alice, venue="pines", body="Venue review")
    dish = alice.send("POST", "/reviews", {"target_type": "menu_item", "venue_id": "64-degrees", "station_id": "64-degrees--triton-grill",
                                           "menu_item_id": item, "rating": 5, "body": "Dish review"}, 201).json()
    venue_review(bob, venue="pines", body="Bob's review")
    moderator.send("POST", f"/moderation/reviews/{dish['id']}", {"action": "hide"}, 200)

    mine = me(alice, "GET", "/reviews")
    assert mine["total"] == 2
    assert [(r["body"], r["target_type"], r["moderation_state"], r["is_mine"]) for r in mine["reviews"]] == [
        ("Dish review", "menu_item", "hidden", True), ("Venue review", "venue", "visible", True)]
    assert mine["reviews"][0]["menu_item"] == {"id": item, "name": "Chicken Rice Bowl"}
    assert [r["body"] for r in me(bob, "GET", "/reviews")["reviews"]] == ["Bob's review"]


def test_your_discussions_list_comments_and_replies_with_context(factory, students):
    alice, bob, moderator = students
    bobs = venue_review(bob, venue="pines", body="Bob's review")
    question = comment(bob, bobs["id"], "Is the pizza good?")
    answer = comment(alice, bobs["id"], "Yes, very", parent_id=question["id"])
    comment(bob, bobs["id"], "Thanks!", parent_id=answer["id"])
    own = venue_review(alice, venue="bistro", body="Alice's review")
    top = comment(alice, own["id"], "Adding a note")

    listing = me(alice, "GET", "/comments")
    assert listing["total"] == 2
    latest, reply = listing["comments"]
    assert (latest["id"], latest["is_reply"], latest["review_author"], latest["venue"]["id"]) == (top["id"], False, "you", "bistro")
    assert (reply["body"], reply["is_reply"], reply["replying_to"], reply["reply_count"]) == ("Yes, very", True, bobs["author_name"], 1)
    assert (reply["review_available"], reply["review_rating"], reply["review_author"]) == (True, 4, bobs["author_name"])
    assert me(bob, "GET", "/comments")["total"] == 2

    moderator.send("POST", f"/moderation/reviews/{bobs['id']}", {"action": "hide"}, 200)
    moderator.send("POST", f"/moderation/comments/{answer['id']}", {"action": "hide"}, 200)
    reply = me(alice, "GET", "/comments")["comments"][1]
    assert (reply["review_available"], reply["moderation_state"]) == (False, "hidden")


def test_private_pages_never_include_participant_ids_or_other_emails(factory, students):
    alice, bob, _ = students
    review = venue_review(bob)
    comment(alice, review["id"], "hello")
    me(alice, "PUT", "/favorites/venues/pines")
    with factory() as session:
        participant_ids = set(session.scalars(select(UserAccount.participant_id)))
    for path in ("/account", "/favorites", "/reviews", "/comments"):
        body = alice.client.get(ME + path).text
        assert "bob@example.com" not in body
        assert not any(pid in body for pid in participant_ids), path


def test_export_and_account_deletion_include_favourites(factory, students):
    alice, bob, _ = students
    item = add_item(factory, station="64-degrees--triton-grill", name="Chicken Rice Bowl")
    me(alice, "PUT", "/favorites/venues/pines")
    me(alice, "PUT", f"/favorites/dishes/{item}")
    me(bob, "PUT", "/favorites/venues/pines")

    exported = alice.client.get("/api/v1/pilot/export").json()
    assert exported["schema_version"] == "stage8.v1"
    assert [v["venue_id"] for v in exported["food_chat"]["favorite_venues"]] == ["pines"]
    assert [d["menu_item_id"] for d in exported["food_chat"]["favorite_dishes"]] == [item]

    assert alice.client.request("DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"},
                                headers={"X-CSRF-Token": alice.token}).status_code == 200
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FoodFavoriteVenue)) == 1  # only Bob's remains
        assert session.scalar(select(func.count()).select_from(FoodFavoriteDish)) == 0
    assert [v["id"] for v in me(bob, "GET", "/favorites")["venues"]] == ["pines"]
