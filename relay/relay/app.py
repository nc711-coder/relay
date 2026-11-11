"""The web API behind the review page.

    uvicorn relay.app:app --reload           then http://127.0.0.1:8000/docs

    GET  /api/emails                 the inbox: the demo emails plus the ones this visitor sent
    GET  /api/emails/{id}            one email with the agent's draft, ticket, reasons and every lookup it made
    POST /api/emails                 send a test email: {"persona" or "from_addr", "from_name", "subject", "body"}
                                     -> the agent runs at once and the result comes back (5 to 15 seconds)
    POST /api/emails/{id}/decision   {"decision": "approved" | "edited" | "rejected", "reply": "..."}
    GET  /api/personas               sample customers to send as, each with something to ask about
    GET  /api/board                  the ticket board
    POST /api/inbound                a new Gmail message from n8n (X-Webhook-Secret = INBOUND_SECRET); the agent
                                     drafts at once and the reply comes back for n8n to save as a Gmail draft
    GET  /health

Visitors are told apart by an X-Visitor header (a random id the page keeps). The 60 demo emails are
shown to everyone and are read-only; test emails are seen and decided only by the visitor who sent them.
Limits: FORMS_PER_HOUR per visitor (default 10), DAILY_EMAILS overall (default 200).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db
from .llm import load_dotenv

load_dotenv()
log = logging.getLogger("relay")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

origins = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app = FastAPI(title="Relay", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

_agent = None
_lock = threading.Lock()


def agent():
    global _agent
    with _lock:
        if _agent is None:
            from .agent import Agent
            from .graphstore import postgres_saver
            _agent = Agent(db.connect, checkpointer=postgres_saver(os.environ["DATABASE_URL"]))
    return _agent


class Limits:
    def __init__(self):
        self.per_hour = int(os.environ.get("FORMS_PER_HOUR") or 10)
        self.per_day = int(os.environ.get("DAILY_EMAILS") or 200)
        self.seen: dict[str, deque] = defaultdict(deque)
        self.day, self.count = date.today(), 0
        self.lock = threading.Lock()

    def allow(self, who: str) -> str | None:
        now = time.time()
        with self.lock:
            if date.today() != self.day:
                self.day, self.count = date.today(), 0
            if self.count >= self.per_day:
                return "The demo has handled its emails for today. Please try again tomorrow."
            q = self.seen[who]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= self.per_hour:
                return "That's a lot of test emails in an hour. Please wait a little and try again."
            q.append(now)
            self.count += 1
        return None


limits = Limits()
VISITOR = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def visitor_id(x_visitor: str | None) -> str | None:
    return x_visitor if x_visitor and VISITOR.match(x_visitor) else None


@functools.lru_cache(maxsize=1)
def _personas() -> tuple:
    return tuple(_build_personas())


def personas() -> list[dict]:
    return [dict(p) for p in _personas()]


def _build_personas() -> list[dict]:
    """Senders a visitor can write as: real customers from the demo data, each with something to ask about."""
    from .support_data import build
    picks = [("Still waiting on my order", "Order stuck in transit for two weeks"),
             ("Pause my subscription", "Has an active coffee subscription"),
             ("Bag arrived torn", "Recent order delivered (try a damaged bag)"),
             ("Change delivery schedule", "A café with wholesale orders"),
             ("Refund request", "Recently received an order")]
    out, emails = [], build()["emails"]
    for subject, hint in picks:
        e = next((x for x in emails if x["subject"] == subject), None)
        if e:
            out.append({"id": e["code"], "name": e["from_name"], "email": e["from_addr"], "hint": hint})
    out.append({"id": "new", "name": "Someone new", "email": "", "hint": "Not a customer yet"})
    return out


class NewEmail(BaseModel):
    persona: str = Field(default="", max_length=10)
    from_addr: str = Field(default="", max_length=200)
    from_name: str = Field(default="", max_length=100)
    subject: str = Field(default="", max_length=150)
    body: str = Field(min_length=3, max_length=3000)


class Decision(BaseModel):
    decision: str = Field(pattern="^(approved|edited|rejected)$")
    reply: str | None = Field(default=None, max_length=5000)


LIST_SQL = """select e.id, e.code, e.received_at, e.from_name, e.from_addr, e.subject, left(e.body, 140), e.source,
                     e.status, e.category, e.urgency, d.needs_human
              from support.emails e left join support.drafts d on d.email_id = e.id
              where e.source = 'demo' or (e.source = 'form' and e.visitor = %s)
              order by e.received_at desc limit 200"""


@app.get("/health")
def health():
    return {"status": "ok", "allowed_origins": origins}


@app.get("/api/personas")
def get_personas():
    return {"personas": personas()}


@app.get("/api/emails")
def list_emails(x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor) or "-"
    with db.connect() as conn:
        rows = conn.execute(LIST_SQL, (v,)).fetchall()
    keys = ["id", "code", "received_at", "from_name", "from_addr", "subject", "snippet", "source", "status",
            "category", "urgency", "needs_human"]
    return {"emails": [dict(zip(keys, r)) for r in rows]}


def load(conn, email_id: int, v: str | None) -> dict:
    row = conn.execute("""select e.id, e.code, e.received_at, e.from_name, e.from_addr, e.subject, e.body, e.source,
                                 e.status, e.category, e.urgency, e.visitor,
                                 d.reply, d.ticket, d.needs_human, d.reasons, d.checks, d.steps, d.decision,
                                 d.final_reply, d.decided_at
                          from support.emails e left join support.drafts d on d.email_id = e.id where e.id = %s""",
                       (email_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No such email.")
    keys = ["id", "code", "received_at", "from_name", "from_addr", "subject", "body", "source", "status", "category",
            "urgency", "visitor", "reply", "ticket", "needs_human", "reasons", "checks", "steps", "decision",
            "final_reply", "decided_at"]
    e = dict(zip(keys, row))
    if e["source"] == "form" and e["visitor"] != v:
        raise HTTPException(404, "No such email.")
    e["mine"] = e["source"] == "form"
    e.pop("visitor")
    return e


@app.get("/api/emails/{email_id}")
def get_email(email_id: int, x_visitor: str | None = Header(default=None)):
    with db.connect() as conn:
        return load(conn, email_id, visitor_id(x_visitor))


@app.post("/api/emails")
def new_email(body: NewEmail, request: Request, x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor)
    if not v:
        return JSONResponse({"detail": "Missing visitor id; reload the page."}, status_code=400)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
          (request.client.host if request.client else "?"))
    why = limits.allow(f"{v}|{ip}")
    if why:
        return JSONResponse({"detail": why}, status_code=429)
    known = {p["id"]: p for p in personas()}
    if body.persona and body.persona != "new":
        p = known.get(body.persona)
        if not p:
            raise HTTPException(400, "Unknown persona.")
        addr, name = p["email"], p["name"]
    else:
        addr = body.from_addr.strip() or f"visitor-{v[:8]}@example.net"
        name = body.from_name.strip() or "Demo visitor"
        if addr.lower().endswith("@example.com"):     # demo customers' addresses: only through a persona
            addr = f"visitor-{v[:8]}@example.net"
    with db.connect() as conn:
        eid = conn.execute("""insert into support.emails (from_addr, from_name, subject, body, source, visitor)
                              values (%s, %s, %s, %s, 'form', %s) returning id""",
                           (addr, name, body.subject.strip() or "(no subject)", body.body.strip(), v)).fetchone()[0]
    try:
        out = agent().start(eid)
    except Exception:
        log.exception("agent failed on email %s", eid)
        return JSONResponse({"detail": "The agent couldn't process that email. Please try again.", "id": eid},
                            status_code=500)
    with db.connect() as conn:
        e = load(conn, eid, v)
    e["seconds"] = out.get("seconds")
    return e


@app.post("/api/emails/{email_id}/decision")
def decide(email_id: int, body: Decision, x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor)
    with db.connect() as conn:
        e = load(conn, email_id, v)
    if not e["mine"]:
        return JSONResponse({"detail": "The demo emails are read-only for everyone. Send your own test email "
                                       "to try approving a reply."}, status_code=403)
    try:
        agent().decide(email_id, body.decision, body.reply)
    except LookupError:
        return JSONResponse({"detail": "This email isn't waiting for a decision."}, status_code=409)
    except ValueError as ex:
        return JSONResponse({"detail": str(ex)}, status_code=400)
    with db.connect() as conn:
        return load(conn, email_id, v)


@app.get("/api/board")
def board(x_visitor: str | None = Header(default=None)):
    """Tickets the agent proposed (waiting on a decision) and tickets created by decisions."""
    v = visitor_id(x_visitor) or "-"
    with db.connect() as conn:
        rows = conn.execute("""select e.id, e.subject, e.from_name, e.status, e.category, d.ticket, d.needs_human,
                                      t.status, t.title, t.action, t.priority
                               from support.emails e join support.drafts d on d.email_id = e.id
                               left join support.tickets t on t.email_id = e.id
                               where e.source = 'demo' or (e.source = 'form' and e.visitor = %s)
                               order by e.received_at desc limit 200""", (v,)).fetchall()
    columns = {"waiting": [], "person": [], "open": [], "done": []}
    for eid, subject, name, status, cat, ticket, human, tstatus, ttitle, taction, tprio in rows:
        ticket = ticket or {}
        card = {"email_id": eid, "title": ttitle or ticket.get("title") or subject, "from": name, "category": cat,
                "action": taction if ttitle else ticket.get("action", ""),
                "priority": tprio or ticket.get("priority") or "normal"}
        if tstatus:
            columns["done" if tstatus == "done" else "open"].append(card)
        elif status == "needs_human":
            columns["person"].append(card)
        elif status == "waiting_approval":
            columns["waiting"].append(card)
    return columns


class Inbound(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    from_addr: str = Field(min_length=3, max_length=300)
    from_name: str = Field(default="", max_length=200)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20000)


QUOTE = re.compile(r"\n(On .{5,200}wrote:|-{2,} ?Original Message ?-{2,}|From: .+\nSent: )", re.S)


def clean_body(text: str) -> str:
    """The new part of an email: quoted earlier messages and '>' lines removed, shortened to 3,000 characters."""
    text = (text or "").replace("\r\n", "\n")
    m = QUOTE.search(text)
    if m:
        text = text[:m.start()]
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith(">")]
    return "\n".join(lines).strip()[:3000] or "(empty email)"


def gmail_as(addr: str) -> str:
    """GMAIL_AS="you.other@gmail.com=noah.tanaka1286@example.com,..." lets your own test address act as one of
    Fernwood's customers, so a demo with real Gmail can look up real (fictional) orders."""
    for pair in (os.environ.get("GMAIL_AS") or "").split(","):
        if "=" in pair:
            a, b = (x.strip().lower() for x in pair.split("=", 1))
            if a == addr.strip().lower():
                return b
    return addr


@app.post("/api/inbound")
def inbound(msg: Inbound, x_webhook_secret: str | None = Header(default=None)):
    import hmac
    secret = os.environ.get("INBOUND_SECRET") or ""
    if not secret or not hmac.compare_digest(x_webhook_secret or "", secret):
        return JSONResponse({"detail": "Not allowed."}, status_code=401)
    addr = gmail_as(msg.from_addr)
    with db.connect() as conn:
        row = conn.execute("select id from support.emails where external_id = %s", (msg.message_id,)).fetchone()
        if row:
            eid, fresh = row[0], False                     # n8n retried: don't draft twice
        else:
            eid, fresh = conn.execute("""insert into support.emails (from_addr, from_name, subject, body, source, external_id)
                                         values (%s, %s, %s, %s, 'gmail', %s) returning id""",
                                      (addr, msg.from_name, msg.subject or "(no subject)", clean_body(msg.body),
                                       msg.message_id)).fetchone()[0], True
    if fresh:
        try:
            agent().start(eid)
        except Exception:
            log.exception("agent failed on Gmail message %s", msg.message_id)
            return JSONResponse({"detail": "The agent failed on this email.", "email_id": eid, "reply": ""},
                                status_code=500)
    with db.connect() as conn:
        e = conn.execute(
            """select e.status, e.category, d.reply, d.needs_human, d.reasons from support.emails e
               left join support.drafts d on d.email_id = e.id where e.id = %s""", (eid,)).fetchone()
    status, category, reply, human, reasons = e
    subject = msg.subject if msg.subject.lower().startswith("re:") else f"Re: {msg.subject}"
    return {"email_id": eid, "status": status, "category": category, "reply": reply or "",
            "needs_human": bool(human), "reasons": reasons or [], "subject": subject, "thread_id": msg.thread_id,
            "to": msg.from_addr}


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    log.exception("unexpected error on %s", request.url.path)
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)
