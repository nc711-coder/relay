from collections import Counter

from relay.support_data import CATEGORIES, build
from relay.tools import NAMES, TOPICS, Tools


def test_same_inbox_every_time(inbox):
    assert [e["body"] for e in inbox["emails"]] == [e["body"] for e in build()["emails"]]


def test_inbox_shape(inbox):
    emails = inbox["emails"]
    assert len(emails) == 60
    assert Counter(e["set"] for e in emails) == {"main": 40, "holdout": 10, "extra": 10}
    assert set(e["key"]["category"] for e in emails) == set(CATEGORIES)
    assert len({e["code"] for e in emails}) == 60


def test_answer_keys_point_at_the_senders_own_orders(conn, inbox):
    for e in inbox["emails"]:
        k = e["key"]
        if k["order_id"]:
            owner = conn.execute("select customer_id from fernwood.orders where order_id = %s", (k["order_id"],)).fetchone()[0]
            assert owner == k["customer_id"], e["code"]
            if k["facts"]:
                assert str(k["order_id"]) in k["facts"][0]


def test_tools_only_see_the_senders_records(conn, inbox):
    a, b = [e for e in inbox["emails"] if e["key"]["order_id"]][:2]
    tools = Tools(conn, a["from_addr"])
    assert tools.call("order_details", {"order_id": a["key"]["order_id"]})["found"]
    other = tools.call("order_details", {"order_id": b["key"]["order_id"]})
    assert other == {"found": False, "note": f"No order #{b['key']['order_id']} belongs to this customer."}
    assert all(o["order_id"] != b["key"]["order_id"] for o in tools.call("recent_orders", {"limit": 10})["orders"])


def test_unknown_sender_sees_nothing(conn):
    t = Tools(conn, "stranger@example.net")
    for name in ("find_customer", "recent_orders", "subscription"):
        assert t.call(name, {})["found"] is False
    assert t.call("order_details", {"order_id": 1})["found"] is False


def test_bad_arguments_are_answered_not_raised(conn):
    t = Tools(conn, "stranger@example.net")
    assert "error" in t.call("drop_table", {})
    assert t.call("order_details", {"order_id": "1 or 1=1"})["found"] is False
    assert "error" in t.call("policy", {"topic": "passwords"})
    assert "error" in t.call("recent_orders", {"bogus": 1})
    assert len(t.log) == 4


def test_policy_and_products(conn):
    t = Tools(conn, "x@example.net")
    assert set(TOPICS) >= {"shipping", "refunds", "subscriptions", "wholesale"}
    assert "$50" in t.call("policy", {"topic": "refunds"})["text"]
    kenya = t.call("product_info", {"name": "Kenya"})["products"]
    assert kenya == [{"name": "Kenya AA", "category": "single_origin", "roast": "light", "bag_size_g": 340, "price": 20.5}]
    assert set(NAMES) == {"find_customer", "recent_orders", "order_details", "subscription", "policy", "product_info"}


def test_stuck_parcels_show_days_in_transit(conn, inbox):
    e = next(e for e in inbox["emails"] if e["subject"] == "Still waiting on my order")
    ship = Tools(conn, e["from_addr"]).call("order_details", {"order_id": e["key"]["order_id"]})["shipping"]
    assert ship["status"] == "in_transit" and ship["business_days_in_transit"] > 8


def test_policy_quotes_and_lost_packages():
    from relay.checks import check_draft, quote_in_policy
    assert quote_in_policy("Unopened coffee and unused equipment can be returned within 30 days of delivery")
    assert not quote_in_policy("Opened coffee can be refunded in full")
    bad = {"reply": "Refund approved.", "offers": [{"offer": "refund", "policy_quote": "Opened coffee can be refunded"}],
           "refund_amount": 15}
    problems, _ = check_draft(bad, [], {"from_addr": "a@x", "body": "", "subject": ""})
    assert problems and "isn't backed" in problems[0]
    delivered = [{"tool": "order_details", "result": {"order_id": 1, "shipping": {"status": "delivered"}}}]
    _, person = check_draft({"reply": "ok", "refund_amount": 0}, delivered,
                            {"from_addr": "a@x", "body": "Tracking says delivered but there's no package.", "subject": ""})
    assert person and "investigates" in person[0]
    in_transit = [{"tool": "order_details", "result": {"order_id": 1, "shipping": {"status": "in_transit"}}}]
    _, person = check_draft({"reply": "ok", "refund_amount": 0}, in_transit,
                            {"from_addr": "a@x", "body": "It hasn't arrived yet.", "subject": ""})
    assert person == []
