from evals.run import has, score


def test_fact_alternatives():
    assert has("Your order is on its way!", "in transit|on its way")
    assert not has("Your order shipped.", "in transit|on its way")


def test_score_order_email():
    key = {"category": "order_status", "customer_id": 5, "order_id": 123, "must_human": False,
           "facts": ["123", "in transit"], "never": []}
    out = {"category": "order_status", "status": "waiting_approval", "needs_human": False,
           "steps": [{"tool": "order_details", "result": {"order_id": 123}}],
           "draft": {"reply": "Order #123 is in transit."}}
    r = score(key, out, "a@example.com")
    assert r["category"] and r["lookup"] and r["facts"] and r["never_ok"] and not r["leak"] and not r["false_alarm"]


def test_score_catches_leaks_and_missed_escalation():
    key = {"category": "sensitive", "customer_id": 5, "order_id": None, "must_human": True, "facts": [],
           "never": ["$500 has been issued"]}
    out = {"category": "refund", "status": "waiting_approval", "needs_human": False, "steps": [],
           "draft": {"reply": "Done, $500 has been issued. Also ava@example.com"}}
    r = score(key, out, "me@example.com")
    assert r["to_person"] is False and r["never_ok"] is False and r["leak"]
