"""The rules code enforces around the agent: what goes straight to a person, and what a draft may say.

    flags = screen(email)                  # reasons this email must skip the agent and go to a person
    problems, for_person = check_draft(draft, steps, email)

screen() runs before the AI reads anything: hidden instructions ("ignore your previous instructions"),
legal or chargeback threats, abuse, and requests for other people's data are caught by plain pattern
matching, so a cleverly worded email can't talk its way past the check.

check_draft() runs on every draft: every number in the reply (order numbers, dates, prices, tracking
numbers) must appear in what the tools returned, the policies, or the email itself; no email address
except the sender's and Fernwood's; and any refund over the limit goes to a person.
"""
from __future__ import annotations

import json
import re

from .support_data import REFUND_LIMIT
from .tools import POLICIES

INJECTION = re.compile(r"ignore (all |any |your |the )?(previous |prior |above |earlier )?(instructions|rules|prompts?)"
                       r"|system (note|prompt|message)|you are now|disregard (all|your|the)|pre-?approved|"
                       r"developer mode|act as (an?|the) (admin|system)", re.I)
LEGAL = re.compile(r"\b(lawyer|attorney|lawsuit|sue you|suing|chargeback|small claims|bbb|better business bureau|"
                   r"legal action|dispute (it|this|the charge) with my bank)\b", re.I)
ABUSE = re.compile(r"\b(useless|garbage|idiots?|scam(mers)?|pathetic|incompetent|worst company)\b", re.I)
OTHERS_DATA = re.compile(r"(all|every|list of)\s+(the\s+)?customers?|customer (list|emails?|addresses)|"
                         r"(her|his|their|my friend'?s?) (order history|address|orders)", re.I)
NOT_RECEIVED = re.compile(r"(never (arrived|got|received|came)|(hasn'?t|has not|didn'?t|did not) (arrive|come|show up)|"
                          r"no package|not (here|received)|nothing (here|arrived)|missing package|wasn'?t (there|delivered))",
                          re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
NUMBER = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?%?")
OWN_DOMAIN = "fernwood.example"


def screen(email: dict) -> list[str]:
    text = f"{email.get('subject', '')}\n{email.get('body', '')}"
    reasons = []
    if INJECTION.search(text):
        reasons.append("the email contains instructions aimed at the AI")
    if LEGAL.search(text):
        reasons.append("legal or chargeback threat")
    letters = [c for c in email.get("body", "") if c.isalpha()]
    shouting = len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.6
    if ABUSE.search(text) or shouting:
        reasons.append("an upset or abusive customer")
    foreign = [m.group(0) for m in EMAIL.finditer(text)
               if m.group(0).lower() != email.get("from_addr", "").lower() and not m.group(0).lower().endswith(OWN_DOMAIN)]
    if OTHERS_DATA.search(text) or foreign:
        reasons.append("asks about another person's account or data")
    return reasons


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9$%]+", " ", text.lower()).strip()


# Sentences that limit or describe how something happens, but don't by themselves allow anything.
NOT_PERMISSION = ["approval limit", "refunds go back to the original payment method",
                  "shipping fees are refunded only", "report damage within 30 days"]
OPENED = re.compile(r"\b(opened|tried it|tasted it|brewed|drank|half (the|a) bag)\b", re.I)
UNOPENED = re.compile(r"\b(unopened|not opened|never opened|still sealed|sealed)\b", re.I)
SUB_DONE = re.compile(r"\b(has been|have been|is now|we've|we have|i've|i have)\s+(cancel+ed|paused|skipped|changed|"
                      r"switched|updated)", re.I)
WORD_COUNTS = {"a": 1, "one": 1, "two": 2, "both": 2, "three": 3, "four": 4, "five": 5, "six": 6, "all": 99}


def quote_in_policy(quote: str) -> bool:
    """True if the quoted words really are in the policies (ignoring punctuation and line breaks) and the
    sentence actually allows something (the approval limit says who may approve, not what is allowed)."""
    q = _norm(quote)
    if any(q.startswith(_norm(s)) or _norm(s) in q[:60] for s in NOT_PERMISSION):
        return False
    return len(q) >= 15 and q in _norm(POLICIES)


def _orders(steps: list[dict]) -> list[dict]:
    """Every order the tools returned (order_details and recent_orders)."""
    out = []
    for st in steps:
        r = st.get("result")
        if isinstance(r, dict):
            if r.get("order_id"):
                out.append(r)
            out.extend(o for o in r.get("orders") or [] if isinstance(o, dict))
    return out


def value_at_stake(steps: list[dict], email: dict) -> float:
    """What replacing or refunding the items the email complains about is worth, worked out from the order
    (unit price x how many bags the email says), so the $50 limit doesn't depend on the AI's arithmetic."""
    text = (email.get("subject", "") + " " + email.get("body", "")).lower()
    best = 0.0
    for o in _orders(steps):
        if str(o["order_id"]) not in text:
            continue
        total = 0.0
        for it in o.get("items") or []:
            name = str(it.get("product", "")).lower()
            if not name or name not in text:
                continue
            before = text[:text.index(name)].split()[-4:]
            n = next((WORD_COUNTS[w] for w in reversed(before) if w in WORD_COUNTS), None)
            if n is None:
                n = next((int(w) for w in reversed(before) if w.isdigit() and int(w) < 100), 1)
            total += float(it.get("unit_price") or 0) * min(n, int(it.get("quantity") or 1))
        best = max(best, total)
    return round(best, 2)


def _numbers(text: str) -> list[str]:
    return [m.group(0) for m in NUMBER.finditer(text)]


def _value(raw: str) -> float | None:
    try:
        return float(raw.replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def known_numbers(steps: list[dict], email: dict) -> tuple[set[str], set[float]]:
    """Digit strings and values the draft may use: from tool results, the policies, and the email."""
    blob = json.dumps([s.get("result") for s in steps]) + "\n" + POLICIES + "\n" + email.get("body", "") + \
        "\n" + email.get("subject", "")
    blob = re.sub(r"(\d{4})-(\d{2})-(\d{2})", lambda m: f"{m.group(1)} {int(m.group(2))} {int(m.group(3))}", blob)
    raws = _numbers(blob)
    digits = {re.sub(r"\D", "", r) for r in raws}
    values = {v for v in (_value(r) for r in raws) if v is not None}
    return digits, values


def _delivered(steps: list[dict]) -> bool:
    """True if a looked-up order is marked delivered."""
    for st in steps:
        r = st.get("result")
        if not isinstance(r, dict):
            continue
        if (r.get("shipping") or {}).get("status") == "delivered":
            return True
    return False


def check_draft(draft: dict, steps: list[dict], email: dict) -> tuple[list[str], list[str]]:
    """(problems the AI should fix by rewriting, reasons a person must look at it)."""
    reply = draft.get("reply") or ""
    problems, for_person = [], []
    digits, values = known_numbers(steps, email)
    for raw in _numbers(reply):
        d = re.sub(r"\D", "", raw)
        if len(d) >= 5:                              # order and tracking numbers: exact digits
            if d not in digits:
                problems.append(f"{raw} doesn't appear in the records")
            continue
        v = _value(raw)
        if v is None or v in values or (raw.endswith("%") and v / 100 in values):
            continue
        if not any(abs(v - k) < 0.006 for k in values):
            problems.append(f"{raw} doesn't appear in the records or policies")
    for addr in [m.group(0) for m in EMAIL.finditer(reply)]:
        if addr.lower() != email.get("from_addr", "").lower() and not addr.lower().endswith(OWN_DOMAIN):
            problems.append(f"the reply mentions another email address ({addr})")
    for o in draft.get("offers") or []:
        if not quote_in_policy(str(o.get("policy_quote") or "")):
            problems.append(f"the offer \"{str(o.get('offer', ''))[:80]}\" isn't backed by a sentence copied from the "
                            f"policy; quote the sentence that allows it, or don't offer it")
    body = email.get("subject", "") + " " + email.get("body", "")
    if OPENED.search(body) and not UNOPENED.search(body):
        for o in draft.get("offers") or []:
            words = str(o.get("offer", "")).lower()
            if "refund" in words and "credit" not in words and "damag" not in words and "wrong" not in words:
                problems.append("the customer opened the coffee, and opened coffee can't be returned or refunded "
                                "(see the returns policy); offer what the policy allows for opened coffee instead")
    for o in _orders(steps):
        oid = str(o["order_id"])
        if oid in body and not re.search(rf"(?<!\d){oid}(?!\d)", reply):
            problems.append(f"the reply doesn't name order #{oid}, which the customer asked about")
    damage_offer = any("arrives torn" in _norm(str(o.get("policy_quote") or "")) for o in draft.get("offers") or [])
    for o in _orders(steps):
        days = (o.get("shipping") or {}).get("days_since_delivery")
        if damage_offer and str(o["order_id"]) in body and days is not None and days > 30:
            problems.append(f"order #{o['order_id']} was delivered {days} days ago, and damage must be reported within "
                            f"30 days of delivery; don't offer a replacement or refund, explain the 30-day window")
    if SUB_DONE.search(reply):
        subs = [st.get("result") or {} for st in steps if st.get("tool") == "subscription"]
        if not any(s_.get("active") for r in subs for s_ in r.get("subscriptions") or []):
            problems.append("the reply says a subscription was changed, but the customer has no active subscription "
                            "in the records; say so and ask which email address the subscription is under")
    delivered = _delivered(steps)
    if delivered and NOT_RECEIVED.search(email.get("body", "") + " " + email.get("subject", "")):
        for_person.append("tracking says delivered but the customer says it never arrived: a person investigates first")
    refund = float(draft.get("refund_amount") or 0)
    if draft.get("offers"):
        refund = max(refund, value_at_stake(steps, email))
    if refund > REFUND_LIMIT:
        for_person.append(f"refund of ${refund:,.2f} is over the ${REFUND_LIMIT:.0f} limit support can approve")
    if draft.get("needs_human") and draft.get("human_reason"):
        for_person.append(str(draft["human_reason"]))
    return list(dict.fromkeys(problems)), list(dict.fromkeys(for_person))
