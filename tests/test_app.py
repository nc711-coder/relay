import os

import pytest
from fastapi.testclient import TestClient

from tests.test_agent import Scripted, call


@pytest.fixture()
def client(conn):
    from tests.conftest import TEST_DB
    os.environ["DATABASE_URL"] = TEST_DB
    conn.execute("delete from support.emails where source = 'form'")
    from relay import app as appmod, db
    from relay.agent import Agent
    good = {"reply": "Hi! It's a light roast. Fernwood Coffee Support", "ticket": {"title": "Roast question",
            "priority": "low", "action": ""}, "refund_amount": 0, "needs_human": False, "human_reason": ""}
    appmod._agent = Agent(db.connect, llm=Scripted({"category": "product_question", "urgency": "low", "summary": "q"},
                                                   [good] * 10, rounds=[[call("product_info", name="Kenya")], []] * 10))
    appmod.limits = appmod.Limits()
    return TestClient(appmod.app)


ME = {"X-Visitor": "visitor-aaaa-1111"}
YOU = {"X-Visitor": "visitor-bbbb-2222"}


def test_inbox_lists_demo_emails(client):
    emails = client.get("/api/emails").json()["emails"]
    assert len(emails) == 60 and all(e["source"] == "demo" for e in emails)


def test_send_test_email_then_approve(client):
    persona = client.get("/api/personas").json()["personas"][0]
    r = client.post("/api/emails", json={"persona": persona["id"], "subject": "Roast?", "body": "Is Kenya AA light?"},
                    headers=ME)
    e = r.json()
    assert r.status_code == 200 and e["status"] == "waiting_approval" and e["from_addr"] == persona["email"]
    assert [s["tool"] for s in e["steps"]] == ["find_customer", "product_info"]
    assert any(x["id"] == e["id"] for x in client.get("/api/emails", headers=ME).json()["emails"])
    assert all(x["id"] != e["id"] for x in client.get("/api/emails", headers=YOU).json()["emails"])
    assert client.get(f"/api/emails/{e['id']}", headers=YOU).status_code == 404
    assert client.post(f"/api/emails/{e['id']}/decision", json={"decision": "approved"}, headers=YOU).status_code == 404
    done = client.post(f"/api/emails/{e['id']}/decision", json={"decision": "approved"}, headers=ME).json()
    assert done["status"] == "sent" and done["final_reply"].startswith("Hi!")
    again = client.post(f"/api/emails/{e['id']}/decision", json={"decision": "approved"}, headers=ME)
    assert again.status_code == 409
    board = client.get("/api/board", headers=ME).json()
    assert any(c["email_id"] == e["id"] for c in board["done"])


def test_demo_emails_are_read_only(client, conn):
    demo_id = conn.execute("select id from support.emails where source = 'demo' limit 1").fetchone()[0]
    r = client.post(f"/api/emails/{demo_id}/decision", json={"decision": "approved"}, headers=ME)
    assert r.status_code == 403


def test_visitors_cant_pose_as_demo_customers(client):
    r = client.post("/api/emails", json={"persona": "new", "from_addr": "noah.tanaka1286@example.com",
                                         "body": "where is my order"}, headers=ME).json()
    assert r["from_addr"].startswith("visitor-")


def test_limits_and_visitor_id(client):
    from relay import app as appmod
    appmod.limits.per_hour = 1
    assert client.post("/api/emails", json={"persona": "new", "body": "hello there"}).status_code == 400
    assert client.post("/api/emails", json={"persona": "new", "body": "hello there"}, headers=ME).status_code == 200
    assert client.post("/api/emails", json={"persona": "new", "body": "hello again"}, headers=ME).status_code == 429


def test_inbound_gmail_message(client, conn, monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", "s3cret")
    monkeypatch.setenv("GMAIL_AS", "me.test@gmail.com=noah.tanaka1286@example.com")
    msg = {"message_id": "gm-1", "thread_id": "th-1", "from_addr": "Me.Test@gmail.com", "from_name": "Me",
           "subject": "Roast?", "body": "Is the Kenya AA light?\n\nOn Mon, someone wrote:\n> old stuff"}
    assert client.post("/api/inbound", json=msg).status_code == 401
    assert client.post("/api/inbound", json=msg, headers={"X-Webhook-Secret": "nope"}).status_code == 401
    r = client.post("/api/inbound", json=msg, headers={"X-Webhook-Secret": "s3cret"}).json()
    assert r["reply"] and r["subject"] == "Re: Roast?" and r["to"] == "Me.Test@gmail.com" and r["thread_id"] == "th-1"
    body, addr = conn.execute("select body, from_addr from support.emails where external_id = 'gm-1'").fetchone()
    assert body == "Is the Kenya AA light?" and addr == "noah.tanaka1286@example.com"
    again = client.post("/api/inbound", json=msg, headers={"X-Webhook-Secret": "s3cret"}).json()
    assert again["email_id"] == r["email_id"]                       # a retry doesn't draft twice
    assert all(e["source"] != "gmail" for e in client.get("/api/emails", headers=ME).json()["emails"])


def test_search_and_delete_own_test_emails(client, conn):
    hits = client.get("/api/emails", params={"q": "wholesale pricing"}).json()["emails"]
    assert hits and all("wholesale" in (h["subject"] + h["snippet"] + (h["category"] or "")).lower() for h in hits)
    assert client.get("/api/emails", params={"q": "zzz-nothing-matches"}).json()["emails"] == []
    assert client.get("/api/emails", params={"q": "100%_"}).status_code == 200      # wildcards are taken literally
    persona = client.get("/api/personas").json()["personas"][0]
    e = client.post("/api/emails", json={"persona": persona["id"], "subject": "Roast?", "body": "Is Kenya AA light?"},
                    headers=ME).json()
    assert [x["id"] for x in client.get("/api/emails", params={"q": "roast? kenya"}, headers=ME).json()["emails"]][0] == e["id"]
    assert e["id"] not in [x["id"] for x in client.get("/api/emails", params={"q": "roast? kenya"}, headers=YOU).json()["emails"]]
    assert client.delete(f"/api/emails/{e['id']}", headers=YOU).status_code == 404       # not yours
    demo_id = conn.execute("select id from support.emails where source = 'demo' limit 1").fetchone()[0]
    assert client.delete(f"/api/emails/{demo_id}", headers=ME).status_code == 403        # demo emails stay
    assert client.delete(f"/api/emails/{e['id']}", headers=ME).json() == {"deleted": e["id"]}
    assert client.get(f"/api/emails/{e['id']}", headers=ME).status_code == 404
    assert conn.execute("select count(*) from support.drafts where email_id = %s", (e["id"],)).fetchone()[0] == 0
