"""Food Chat account-deletion policy: a deleted participant's contributions are permanently
deleted, other people's replies are kept and moved up their thread, and nothing else changes.

Scenario (A is deleted; B and C stay):

    A's review of Pines (RA)                     -> deleted with its whole thread
        b1 (B) -> c1 (C)                            deleted (discussion of RA)
        votes on b1, reports on RA and b1           deleted
    B's review of 64 Degrees (RB)                -> kept
        x1 (C)
            a1 (A)                                  deleted
                y1 (B)                              kept, moved up to x1
                    a2 (A)                          deleted
                        z1 (C)                      kept, moved up to y1
            q1 (B)                                  kept, untouched
        a4 (A)                                      deleted
            w1 (C)                                  kept, becomes top level
            a5 (A)                                  deleted
                v1 (B)                              kept, becomes top level (a5 and a4 both gone)
    A's and B's dish reviews of one item; C's review of Pines   -> A's deleted, others kept
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app import pilot_routes
from backend.app.food_catalog import menu_name_key
from backend.app.food_chat import delete_participant_food_chat
from backend.app.food_models import (
    FoodComment,
    FoodCommentVote,
    FoodMenuItem,
    FoodReport,
    FoodReview,
    ReportReason,
    ReviewTarget,
)
from backend.app.main import app
from backend.app.models import Participant, UserAccount
from backend.tests.test_accounts import accept_consent, signup
from backend.tests.test_food_api import NOW, SOURCE, factory  # noqa: F401  (seeded, FK-enforcing database)

DELETE_BODY = {"confirmation": "DELETE_MY_DATA"}


def build_scenario(session, a, b, c):
    """Create the scenario above. Returns {label: id}."""
    ids = {}

    def add(label, record):
        session.add(record)
        session.flush()
        ids[label] = record.id
        return record

    item = add("item", FoodMenuItem(station_id="64-degrees--triton-grill", name="Chicken Rice Bowl",
                                    name_key=menu_name_key("Chicken Rice Bowl"), source_url=SOURCE, verified_at=NOW))
    venue = lambda author, venue_id: FoodReview(participant_id=author, target_type=ReviewTarget.venue, venue_id=venue_id, rating=4, body="")  # noqa: E731
    dish = lambda author: FoodReview(participant_id=author, target_type=ReviewTarget.menu_item, venue_id="64-degrees",  # noqa: E731
                                     station_id="64-degrees--triton-grill", menu_item_id=item.id, rating=3, body="")
    ra = add("RA", venue(a, "pines"))
    rb = add("RB", venue(b, "64-degrees"))
    add("C-pines", venue(c, "pines"))
    add("A-dish", dish(a))
    add("B-dish", dish(b))

    def comment(label, author, review, parent=None):
        return add(label, FoodComment(review_id=review.id, parent_id=ids[parent] if parent else None, participant_id=author, body=label))

    comment("b1", b, ra)
    comment("c1", c, ra, "b1")
    comment("x1", c, rb)
    comment("a1", a, rb, "x1")
    comment("y1", b, rb, "a1")
    comment("a2", a, rb, "y1")
    comment("z1", c, rb, "a2")
    comment("q1", b, rb, "x1")
    comment("a4", a, rb)
    comment("w1", c, rb, "a4")
    comment("a5", a, rb, "a4")
    comment("v1", b, rb, "a5")

    def vote(label, author, target, value=1):
        add(label, FoodCommentVote(comment_id=ids[target], participant_id=author, value=value))

    vote("vote C on b1", c, "b1")         # thread of A's review -> deleted
    vote("vote A on x1", a, "x1")         # A's own vote -> deleted
    vote("vote B on a1", b, "a1")         # vote on A's comment -> deleted
    vote("vote C on y1", c, "y1", -1)     # unrelated -> kept
    vote("vote B on z1", b, "z1")         # unrelated -> kept

    def report(label, author, review=None, comment_label=None):
        add(label, FoodReport(participant_id=author, review_id=ids[review] if review else None,
                              comment_id=ids[comment_label] if comment_label else None, reason=ReportReason.spam))

    report("report B on RA", b, review="RA")            # on A's review -> deleted
    report("report C on b1", c, comment_label="b1")     # in A's review thread -> deleted
    report("report A on RB", a, review="RB")            # by A -> deleted
    report("report A on x1", a, comment_label="x1")     # by A -> deleted
    report("report B on a1", b, comment_label="a1")     # on A's comment -> deleted
    report("report C on RB", c, review="RB")            # unrelated -> kept
    report("report B on w1", b, comment_label="w1")     # unrelated -> kept
    session.commit()
    return ids


def snapshot(session, ids):
    """What remains, in scenario labels: reviews, comments with their parents, votes, reports."""
    label = {value: key for key, value in ids.items()}
    return {
        "reviews": sorted(label[v] for v in session.scalars(select(FoodReview.id))),
        "comments": dict(sorted(
            (label[cid], label.get(parent)) for cid, parent in session.execute(select(FoodComment.id, FoodComment.parent_id))
        )),
        "votes": sorted(label[v] for v in session.scalars(select(FoodCommentVote.id))),
        "reports": sorted(label[v] for v in session.scalars(select(FoodReport.id))),
    }


EXPECTED_AFTER_DELETING_A = {
    "reviews": ["B-dish", "C-pines", "RB"],
    "comments": {"q1": "x1", "v1": None, "w1": None, "x1": None, "y1": "x1", "z1": "y1"},
    "votes": ["vote B on z1", "vote C on y1"],
    "reports": ["report B on w1", "report C on RB"],
}


def participants(factory, count):  # noqa: F811
    with factory() as session:
        values = [Participant() for _ in range(count)]
        session.add_all(values)
        session.commit()
        return [value.id for value in values]


def assert_no_orphans(session):
    """Every reply's parent exists and is in the same review thread."""
    rows = session.execute(select(FoodComment.id, FoodComment.parent_id, FoodComment.review_id)).all()
    thread_of = {cid: review for cid, _, review in rows}
    for cid, parent, review in rows:
        assert parent is None or thread_of.get(parent) == review, cid


def test_policy_deletes_contributions_and_moves_other_replies_up(factory):  # noqa: F811
    a, b, c = participants(factory, 3)
    with factory() as session:
        ids = build_scenario(session, a, b, c)
        result = delete_participant_food_chat(session, a)
        session.commit()

        assert snapshot(session, ids) == EXPECTED_AFTER_DELETING_A
        assert_no_orphans(session)
        # Reviews RA and A-dish; comments b1, c1 (RA's thread) and a1, a2, a4, a5 (A's own);
        # votes C-on-b1, B-on-a1, A-on-x1; reports B-on-RA, C-on-b1, B-on-a1, A-on-RB, A-on-x1;
        # replies y1, z1, w1, v1 moved up.
        assert (result.reviews, result.comments, result.votes, result.reports, result.replies_reparented) == (2, 6, 3, 5, 4)
        for table in (FoodReview, FoodComment, FoodCommentVote, FoodReport):
            assert session.scalar(select(func.count()).select_from(table).where(table.participant_id == a)) == 0


def test_deleting_again_or_a_participant_with_no_food_chat_changes_nothing(factory):  # noqa: F811
    a, b, c, d = participants(factory, 4)
    with factory() as session:
        ids = build_scenario(session, a, b, c)
        delete_participant_food_chat(session, a)
        session.commit()
        before = snapshot(session, ids)
        assert vars(delete_participant_food_chat(session, a)) == {"reviews": 0, "comments": 0, "votes": 0, "reports": 0, "replies_reparented": 0, "favorites": 0, "messages": 0, "ratings": 0}
        assert vars(delete_participant_food_chat(session, d)) == {"reviews": 0, "comments": 0, "votes": 0, "reports": 0, "replies_reparented": 0, "favorites": 0, "messages": 0, "ratings": 0}
        session.commit()
        assert snapshot(session, ids) == before


def test_a_reply_chain_of_only_the_deleted_participant_disappears_entirely(factory):  # noqa: F811
    a, b = participants(factory, 2)
    with factory() as session:
        review = FoodReview(participant_id=b, target_type=ReviewTarget.venue, venue_id="pines", rating=5, body="")
        session.add(review)
        session.flush()
        top = FoodComment(review_id=review.id, participant_id=a, body="1")
        session.add(top)
        session.flush()
        middle = FoodComment(review_id=review.id, parent_id=top.id, participant_id=a, body="2")
        session.add(middle)
        session.flush()
        session.add(FoodComment(review_id=review.id, parent_id=middle.id, participant_id=a, body="3"))
        session.commit()

        assert delete_participant_food_chat(session, a).comments == 3
        session.commit()
        assert session.scalar(select(func.count()).select_from(FoodComment)) == 0
        assert session.get(FoodReview, review.id) is not None  # B's review is untouched


# Through the real account-deletion endpoint ------------------------------------------------------

def signed_up(email):
    client = TestClient(app)
    assert signup(client, email=email).status_code == 201
    return client, accept_consent(client)


def test_account_deletion_applies_the_policy(factory):  # noqa: F811
    alice, token = signed_up("alice@example.com")
    b, c = participants(factory, 2)
    with factory() as session:
        a = session.scalar(select(UserAccount.participant_id))
        ids = build_scenario(session, a, b, c)

    response = alice.request("DELETE", "/api/v1/pilot/account", json=DELETE_BODY, headers={"X-CSRF-Token": token})

    assert response.status_code == 200, response.text
    with factory() as session:
        assert snapshot(session, ids) == EXPECTED_AFTER_DELETING_A
        assert_no_orphans(session)
        assert session.get(Participant, a).deleted_at is not None
        assert session.scalar(select(func.count()).select_from(UserAccount)) == 0


def test_account_deletion_is_all_or_nothing(factory, monkeypatch):  # noqa: F811
    alice, token = signed_up("alice@example.com")
    b, c = participants(factory, 2)
    with factory() as session:
        a = session.scalar(select(UserAccount.participant_id))
        ids = build_scenario(session, a, b, c)
        before = snapshot(session, ids)

    def fail(*_args, **_kwargs):  # the session-revocation step runs after Food Chat deletion
        raise RuntimeError("simulated failure late in account deletion")

    monkeypatch.setattr(pilot_routes, "update", fail)
    response = TestClient(app, raise_server_exceptions=False, cookies=alice.cookies).request(
        "DELETE", "/api/v1/pilot/account", json=DELETE_BODY, headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 500
    with factory() as session:
        assert snapshot(session, ids) == before  # Food Chat untouched
        assert session.get(Participant, a).deleted_at is None
        assert session.scalar(select(func.count()).select_from(UserAccount)) == 1
