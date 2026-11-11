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


def quote_in_policy(quote: str) -> bool:
    """True if the quoted words really are in the policies (ignoring punctuation and line breaks)."""
    q = _norm(quote)
    return len(q) >= 15 and q in _norm(POLICIES)


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
    delivered = _delivered(steps)
    if delivered and NOT_RECEIVED.search(email.get("body", "") + " " + email.get("subject", "")):
        for_person.append("tracking says delivered but the customer says it never arrived: a person investigates first")
    refund = float(draft.get("refund_amount") or 0)
    if refund > REFUND_LIMIT:
        for_person.append(f"refund of ${refund:,.2f} is over the ${REFUND_LIMIT:.0f} limit support can approve")
    if draft.get("needs_human") and draft.get("human_reason"):
        for_person.append(str(draft["human_reason"]))
    return list(dict.fromkeys(problems)), list(dict.fromkeys(for_person))
