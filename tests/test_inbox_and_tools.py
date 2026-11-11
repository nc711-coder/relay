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


def test_opened_coffee_order_numbers_and_value_at_stake():
    from relay.checks import check_draft, quote_in_policy, value_at_stake
    # the approval limit says who may approve, not what is allowed
    assert not quote_in_policy("Approval limit: support can approve on its own a refund, credit or free replacement")
    order = [{"tool": "order_details", "result": {"order_id": 24712, "shipping": {"status": "delivered"},
              "items": [{"product": "Brazil Cerrado 1kg", "quantity": 6, "unit_price": 30.8, "line_total": 184.8}]}}]
    opened = {"from_addr": "a@x", "subject": "Refund request",
              "body": "I didn't like the Brazil Cerrado 1kg in order #24712. I opened it and tried it."}
    refund = {"reply": "We can refund order #24712.", "refund_amount": 30.8,
              "offers": [{"offer": "refund of the bag", "policy_quote": "Unopened coffee and unused equipment can be "
                          "returned within 30 days of delivery for a full refund of the item price."}]}
    problems, _ = check_draft(refund, order, opened)
    assert any("opened the coffee" in p for p in problems)
    problems, _ = check_draft({"reply": "Sorry to hear that.", "refund_amount": 0}, order, opened)
    assert any("#24712" in p for p in problems)
    split = {"from_addr": "a@x", "subject": "", "body": "Two of the Brazil Cerrado 1kg bags in order #24712 arrived split."}
    assert value_at_stake(order, split) == 61.6
    replace = {"reply": "We'll replace both bags from order #24712.", "refund_amount": 30.8,
               "offers": [{"offer": "replace two bags", "policy_quote": "If a bag arrives torn, damaged, or the wrong "
                           "coffee is sent, we replace it free or refund that item, whichever the customer prefers."}]}
    problems, person = check_draft(replace, order, split)
    assert not problems and person and "$61.60" in person[0]


def test_late_damage_and_subscription_claims():
    from relay.checks import check_draft
    old = [{"tool": "order_details", "result": {"order_id": 24657, "shipping": {"status": "delivered", "days_since_delivery": 60},
            "items": [{"product": "Night Owl Dark Roast", "quantity": 1, "unit_price": 15.5, "line_total": 15.5}]}}]
    email = {"from_addr": "a@x", "subject": "", "body": "My Night Owl Dark Roast arrived torn. Order 24657."}
    replace = {"reply": "We'll replace the bag from order #24657.", "refund_amount": 15.5,
               "offers": [{"offer": "replace", "policy_quote": "If a bag arrives torn, damaged, or the wrong coffee is "
                           "sent, we replace it free or refund that item, whichever the customer prefers."}]}
    problems, _ = check_draft(replace, old, email)
    assert any("60 days ago" in p for p in problems)
    none = [{"tool": "subscription", "result": {"found": False, "subscriptions": []}}]
    problems, _ = check_draft({"reply": "Your subscription has been cancelled.", "refund_amount": 0}, none,
                              {"from_addr": "a@x", "subject": "", "body": "Please cancel my subscription."})
    assert any("no active subscription" in p for p in problems)


def test_product_search_ignores_filler_words(conn, inbox):
    from relay.tools import Tools
    t = Tools(conn, "nobody@example.net")
    assert [p["name"] for p in t.product_info("the Burr Grinder price")["products"]] == ["Burr Grinder"]


def test_no_claimed_changes_and_one_sign_off():
    from relay.checks import check_draft, sign_off
    problems, _ = check_draft({"reply": "I’ve updated your account to every two weeks.", "refund_amount": 0}, [],
                              {"from_addr": "a@x", "subject": "", "body": "Can we switch to every two weeks?"})
    assert any("already made" in p for p in problems)
    problems, _ = check_draft({"reply": "We'll switch you to every two weeks from your next delivery.", "refund_amount": 0},
                              [], {"from_addr": "a@x", "subject": "", "body": "Can we switch to every two weeks?"})
    assert problems == []
    assert sign_off("Hi,\n\nDone soon. Fernland Coffee Support") == "Hi,\n\nDone soon.\n\nFernwood Coffee Support"
    assert sign_off("Hi,\n\nThanks for your patience.\n\nBest regards,\nFernwood Coffee Support").endswith(
        "Thanks for your patience.\n\nFernwood Coffee Support")
    assert sign_off("Hi Ava,\n\nYour order shipped.") == "Hi Ava,\n\nYour order shipped.\n\nFernwood Coffee Support"


def test_tidy_money_and_greeting():
    from relay.checks import tidy
    assert tidy("A refund of $75.5 and $1,234.5, not $15.50 or $129.") == "A refund of $75.50 and $1,234.50, not $15.50 or $129."
    assert tidy("Hi Lantern Coffee House,\nWe can switch.") == "Hi Lantern Coffee House,\n\nWe can switch."
    assert tidy("Hi Ava,\n\nAlready spaced.") == "Hi Ava,\n\nAlready spaced."
    assert tidy("Hi Ava, your order #27989 is in transit.") == "Hi Ava,\n\nYour order #27989 is in transit."
    assert tidy("Hi, I can help.") == "Hi,\n\nI can help."
    assert tidy("Your order shipped. Hi there, again.") == "Your order shipped. Hi there, again."


def test_greeting_is_always_there():
    from relay.checks import greet, greeting_name
    cafe = [{"tool": "find_customer", "result": {"found": True, "name": "Lantern Coffee House", "type": "wholesale"}}]
    person = [{"tool": "find_customer", "result": {"found": True, "name": "Ava Tanaka", "type": "retail"}}]
    assert greeting_name({}, cafe) == "Lantern Coffee House" and greeting_name({}, person) == "Ava"
    assert greeting_name({"from_name": "Dana (Hilltop Bakery)"}, [{"tool": "find_customer", "result": {"found": False}}]) == "Dana"
    assert greet("We can change your schedule.", "Lantern Coffee House") == "Hi Lantern Coffee House,\n\nWe can change your schedule."
    assert greet("Hi Ava,\n\nYour order shipped.", "Ava") == "Hi Ava,\n\nYour order shipped."
