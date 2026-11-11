"""The agent's graph with a scripted AI (no API key needed): what it looks up, when it stops for a person,
and that nothing finishes without a decision."""
import json
from types import SimpleNamespace

import pytest

from relay import db
from relay.agent import Agent

pytestmark = pytest.mark.usefixtures("conn")


def call(tool, **args):
    return SimpleNamespace(id=f"c-{tool}", function=SimpleNamespace(name=tool, arguments=json.dumps(args)))


class Scripted:
    """Answers sort/draft from queues; tool_step from a list of rounds (each a list of tool calls)."""
    model = "scripted"

    def __init__(self, sort, drafts, rounds=()):
        self.sort, self.drafts, self.rounds = sort, list(drafts), list(rounds)
        self.prompts = []

    def json(self, system, user, schema=None, name="", max_tokens=0):
        self.prompts.append((name, user))
        return (self.sort if name == "sort" else self.drafts.pop(0)), {}

    def tool_step(self, messages, tools, max_tokens=0):
        calls = self.rounds.pop(0) if self.rounds else []
        return SimpleNamespace(content="done" if not calls else "", tool_calls=calls)


@pytest.fixture()
def url(conn):
    from tests.conftest import TEST_DB
    conn.execute("delete from support.tickets; delete from support.drafts")
    conn.execute("update support.emails set status = 'new'")
    return TEST_DB


def email(conn, code_prefix_subject):
    row = conn.execute("select id, from_addr from support.emails where subject = %s order by id limit 1",
                       (code_prefix_subject,)).fetchone()
    return row


def make(url, llm):
    return Agent(lambda: db.connect(url), llm=llm)


def test_order_question_drafted_then_sent_after_approval(conn, url, inbox):
    e = next(x for x in inbox["emails"] if x["subject"] == "Still waiting on my order")
    eid = conn.execute("select id from support.emails where code = %s", (e["code"],)).fetchone()[0]
    oid = e["key"]["order_id"]
    llm = Scripted({"category": "order_status", "urgency": "normal", "summary": "where is it"},
                   [{"reply": f"Your order #{oid} has been in transit too long, so we'll send a replacement.",
                     "ticket": {"title": "Replace stuck order", "priority": "normal", "action": f"resend order #{oid}"},
                     "refund_amount": 0, "needs_human": False, "human_reason": ""}],
                   rounds=[[call("order_details", order_id=oid), call("policy", topic="shipping")]])
    a = make(url, llm)
    out = a.start(eid)
    assert out["status"] == "waiting_approval" and "__interrupt__" in out
    assert [s["tool"] for s in out["steps"]] == ["find_customer", "order_details", "policy"]
    assert conn.execute("select status from support.emails where id = %s", (eid,)).fetchone()[0] == "waiting_approval"
    assert conn.execute("select count(*) from support.tickets where email_id = %s", (eid,)).fetchone()[0] == 0
    done = a.decide(eid, "approved")
    assert done["status"] == "sent"
    st, reply = conn.execute("""select e.status, d.final_reply from support.emails e join support.drafts d
                                on d.email_id = e.id where e.id = %s""", (eid,)).fetchone()
    assert st == "sent" and str(oid) in reply
    assert conn.execute("select status from support.tickets where email_id = %s", (eid,)).fetchone()[0] == "open"
    with pytest.raises(LookupError):
        a.decide(eid, "approved")                           # can't be decided twice


def test_hidden_instructions_skip_the_ai_and_tools(conn, url, inbox):
    e = next(x for x in inbox["emails"] if x["subject"] == "Urgent refund")
    eid = conn.execute("select id from support.emails where code = %s", (e["code"],)).fetchone()[0]
    llm = Scripted({"category": "refund", "urgency": "high", "summary": "refund"}, [])
    out = make(url, llm).start(eid)
    assert out["category"] == "sensitive" and out["needs_human"]
    # the AI never drafts; code only looks up the account and recent orders for the person picking it up
    assert {s["tool"] for s in out["steps"]} <= {"find_customer", "recent_orders"}
    assert "$500" not in out["draft"]["reply"]
    assert out["status"] == "needs_human"


def test_spam_gets_no_reply(conn, url, inbox):
    e = next(x for x in inbox["emails"] if x["key"]["category"] == "spam")
    eid = conn.execute("select id from support.emails where code = %s", (e["code"],)).fetchone()[0]
    out = make(url, Scripted({"category": "spam", "urgency": "low", "summary": "ad"}, [])).start(eid)
    assert out["status"] == "no_reply" and "__interrupt__" not in out


def test_invented_number_gets_one_rewrite_then_a_person(conn, url, inbox):
    e = next(x for x in inbox["emails"] if x["subject"] == "Still waiting on my order")
    eid = conn.execute("select id from support.emails where code = %s", (e["code"],)).fetchone()[0]
    bad = {"reply": "Your order #99999999 ships tomorrow.", "ticket": {}, "refund_amount": 0,
           "needs_human": False, "human_reason": ""}
    llm = Scripted({"category": "order_status", "urgency": "normal", "summary": "x"}, [bad, bad])
    out = make(url, llm).start(eid)
    assert out["rewrites"] == 1 and out["needs_human"]
    assert any("couldn't be verified" in r for r in out["reasons"])
    assert "don't match the records" in llm.prompts[-1][1] and "99999999" in llm.prompts[-1][1]


def test_refund_over_limit_goes_to_a_person(conn, url, inbox):
    e = next(x for x in inbox["emails"] if x["subject"] == "Full refund please")
    eid = conn.execute("select id from support.emails where code = %s", (e["code"],)).fetchone()[0]
    llm = Scripted({"category": "refund", "urgency": "normal", "summary": "refund"},
                   [{"reply": "We're sorry to hear that.", "ticket": {}, "refund_amount": 75.0,
                     "needs_human": False, "human_reason": ""}])
    out = make(url, llm).start(eid)
    assert out["needs_human"] and "over the $50 limit" in out["reasons"][0]


def test_edit_and_reject(conn, url, inbox):
    ids = [r[0] for r in conn.execute("""select id from support.emails where subject = 'Question' order by id limit 2""")]
    good = {"reply": "Yes!", "ticket": {"title": "q", "priority": "low", "action": ""}, "refund_amount": 0,
            "needs_human": False, "human_reason": ""}
    for eid, (decision, reply) in zip(ids, [("edited", "Yes, it is a light roast."), ("rejected", None)]):
        a = make(url, Scripted({"category": "product_question", "urgency": "low", "summary": "q"}, [good]))
        a.start(eid)
        out = a.decide(eid, decision, reply)
        row = conn.execute("""select e.status, d.decision, d.final_reply from support.emails e
                              join support.drafts d on d.email_id = e.id where e.id = %s""", (eid,)).fetchone()
        assert row == (("sent", "edited", "Yes, it is a light roast.") if decision == "edited" else ("rejected", "rejected", None))
    with pytest.raises(ValueError):
        a.decide(ids[0], "edited", "")
