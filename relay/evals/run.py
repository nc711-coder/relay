"""Run the agent on the labeled emails and score it against their answer keys.

    python -m evals.run                    the 40 main emails   -> evals/reports/agent-<model>.md
    python -m evals.run --set holdout      the 10 held-out emails (never used to tune the prompts)
    python -m evals.run --only e03 e17     just these

Each email runs until the agent stops for a person, exactly as in the app; nothing is approved or sent.
Needs DATABASE_URL and GROQ_API_KEY in .env, and the inbox loaded (python -m relay.db).
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from relay import db
from relay.agent import Agent
from relay.llm import load_dotenv
from relay.support_data import build

REPORTS = Path(__file__).resolve().parent / "reports"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def has(text: str, fact: str) -> bool:
    t = text.lower()
    return any(alt.strip().lower() in t for alt in fact.split("|"))


def score(key: dict, out: dict, sender: str) -> dict:
    reply = (out.get("draft") or {}).get("reply", "") if out.get("status") != "no_reply" else ""
    steps = out.get("steps") or []
    blob = json.dumps([s.get("result") for s in steps])
    r = {"category": out.get("category") == key["category"]}
    if key["order_id"]:
        r["lookup"] = f'"order_id": {key["order_id"]}' in blob
    elif key["customer_id"] is None and key["category"] not in ("spam", "sensitive"):
        r["lookup"] = '"found": false' in blob
    human = bool(out.get("needs_human"))
    r["to_person"] = human == key["must_human"] if key["must_human"] else None
    r["false_alarm"] = human and not key["must_human"]
    if key["category"] == "spam":
        r["facts"] = out.get("status") == "no_reply"
    elif key["facts"] and not key["must_human"]:
        missing = [f for f in key["facts"] if not has(reply, f)]
        r["facts"] = not missing
        r["missing"] = missing
    r["never_ok"] = not any(has(reply, n) for n in key["never"])
    others = [a for a in (m.group(0) for m in EMAIL.finditer(reply))
              if a.lower() != sender.lower() and not a.lower().endswith("fernwood.example")]
    r["leak"] = bool(others)
    r["unverified"] = bool((out.get("problems") or []) and not out.get("needs_human"))
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["main", "holdout", "extra"], default="main")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between emails (Groq's rate limit)")
    args = ap.parse_args()
    load_dotenv()

    emails = [e for e in build()["emails"] if e["set"] == args.set and (not args.only or e["code"] in args.only)]
    agent = Agent(db.connect)
    model = getattr(agent.llm, "model", "model")
    with db.connect() as conn:
        ids = dict(conn.execute("select code, id from support.emails where code is not null").fetchall())
    rows = []
    for n, e in enumerate(emails, start=1):
        t = time.perf_counter()
        try:
            out = agent.start(ids[e["code"]])
            err = ""
        except Exception as ex:                       # one broken email shouldn't stop the run
            out, err = {}, f"{type(ex).__name__}: {ex}"
        secs = round(time.perf_counter() - t, 1)
        r = score(e["key"], out, e["from_addr"])
        rows.append({"code": e["code"], "subject": e["subject"], "key": e["key"], "secs": secs, "error": err,
                     "category": out.get("category"), "needs_human": out.get("needs_human"), "reasons": out.get("reasons"),
                     "tools": [s["tool"] for s in out.get("steps") or []],
                     "reply": (out.get("draft") or {}).get("reply", ""), **r})
        ok = all(v for k, v in r.items() if k in ("category", "lookup", "to_person", "facts", "never_ok") and v is not None) \
            and not r["leak"] and not err
        print(f"[{n:>2}/{len(emails)}] {e['code']} {'OK  ' if ok else 'MISS'} {secs:>5}s  {e['key']['category']:16} {e['subject'][:50]}")
        time.sleep(args.pause)

    def rate(k, rows_=rows):
        vals = [r[k] for r in rows_ if r.get(k) is not None]
        return f"{sum(vals)}/{len(vals)} ({100 * sum(vals) / len(vals):.0f}%)" if vals else "–"
    lines = [f"# Agent check ({args.set}): {model}, {datetime.now():%Y-%m-%d %H:%M}", "",
             "| Check | Result | Target |", "| --- | --- | --- |",
             f"| Sorted into the right category | {rate('category')} | 95% |",
             f"| Looked up the right order (or saw the sender isn't a customer) | {rate('lookup')} | 95% |",
             f"| Reply contains the key facts | {rate('facts')} | 90% |",
             f"| Sent to a person when it should be | {rate('to_person')} | 100% |",
             f"| Never said what it mustn't | {rate('never_ok')} | 100% |",
             f"| Sent to a person when it didn't need to be | {sum(r['false_alarm'] for r in rows)} | low |",
             f"| Showed another customer's data | **{sum(r['leak'] for r in rows)}** | 0 |",
             f"| Unverified facts that reached the draft unflagged | **{sum(r['unverified'] for r in rows)}** | 0 |",
             f"| Errors | {sum(bool(r['error']) for r in rows)} | 0 |", "",
             f"Median seconds per email: {sorted(r['secs'] for r in rows)[len(rows) // 2] if rows else 0}", "",
             "## Misses", ""]
    for r in rows:
        bad = [k for k in ("category", "lookup", "to_person", "facts", "never_ok") if r.get(k) is False]
        if r["leak"]:
            bad.append("leak")
        if r["error"]:
            bad.append("error")
        if bad:
            lines.append(f"- **{r['code']}** {r['subject']} ({r['key']['category']}): {', '.join(bad)}")
            lines.append(f"  - got category {r['category']}, to person: {r['needs_human']} {r['reasons'] or ''}")
            if r.get("missing"):
                lines.append(f"  - missing facts: {r['missing']}")
            lines.append(f"  - tools: {r['tools']}")
            if r["error"]:
                lines.append(f"  - error: {r['error']}")
            lines.append(f"  - reply: {' '.join(r['reply'].split())[:400]}")
    REPORTS.mkdir(exist_ok=True)
    name = f"agent-{model.split('/')[-1]}-{args.set}" + ("-partial" if args.only else "")
    (REPORTS / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / f"{name}.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print("\n" + "\n".join(lines[:14]) + f"\n\nFull report: evals/reports/{name}.md")


if __name__ == "__main__":
    main()
