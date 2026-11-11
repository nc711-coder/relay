"""Set up Relay's tables and the demo inbox.

    python -m relay.db            load the demo inbox (keeps Fernwood's data if it's already there)
    python -m relay.db --reset    also empty the inbox of emails sent through the demo form

.env: DATABASE_URL (the same Supabase project as Tally). If Fernwood's data isn't there yet, it's loaded first.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .fernwood import COLUMNS, generate
from .llm import load_dotenv
from .support_data import build

ROOT = Path(__file__).resolve().parent.parent


def connect(url: str | None = None, **kw):
    import psycopg
    return psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True, prepare_threshold=None, **kw)


def fernwood_loaded(conn) -> bool:
    return bool(conn.execute("select to_regclass('fernwood.orders')").fetchone()[0])


def load_fernwood(conn) -> None:
    tables = generate()
    conn.execute((ROOT / "sql" / "fernwood.sql").read_text(encoding="utf-8"))
    with conn.transaction():
        for name, cols in COLUMNS.items():
            with conn.cursor() as cur, cur.copy(f"copy fernwood.{name} ({', '.join(cols)}) from stdin") as cp:
                for row in tables[name]:
                    cp.write_row(row)


def load(url: str | None = None) -> dict:
    data = build()
    with connect(url) as conn:
        if not fernwood_loaded(conn):
            load_fernwood(conn)
        conn.execute((ROOT / "sql" / "support.sql").read_text(encoding="utf-8"))
        with conn.transaction():
            with conn.cursor() as cur, cur.copy("copy support.customer_emails (customer_id, email) from stdin") as cp:
                for r in data["customer_emails"]:
                    cp.write_row((r["customer_id"], r["email"]))
            cols = ["order_id", "carrier", "tracking", "status", "shipped_on", "delivered_on", "estimated_delivery"]
            with conn.cursor() as cur, cur.copy(f"copy support.shipments ({', '.join(cols)}) from stdin") as cp:
                for r in data["shipments"]:
                    cp.write_row([r[c] for c in cols])
            for e in data["emails"]:
                conn.execute("""insert into support.emails (code, received_at, from_addr, from_name, subject, body, source)
                                values (%s, %s, %s, %s, %s, %s, 'demo')""",
                             (e["code"], e["received_at"], e["from_addr"], e["from_name"], e["subject"], e["body"]))
    return {"customer emails": len(data["customer_emails"]), "shipments": len(data["shipments"]),
            "demo emails": len(data["emails"])}


def main() -> int:
    load_dotenv()
    if not os.environ.get("DATABASE_URL"):
        print("Set DATABASE_URL in .env first (the same one as Tally).")
        return 2
    print("Setting up the support inbox...")
    for k, v in load().items():
        print(f"  {k:16} {v:>6,}")
    print("Done. The demo inbox has its emails; the agent hasn't drafted anything yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
