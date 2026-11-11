"""Let the agent draft replies for the demo emails ahead of time, so the live demo shows them instantly.

    python -m relay.prepare          drafts every demo email that doesn't have one yet (about 5 to 8 minutes)
    python -m relay.prepare --all    redo all 60

Uses the same agent and saved-graph store as the app.
"""
from __future__ import annotations

import os
import sys
import time

from . import db
from .llm import load_dotenv


def main(argv: list[str]) -> int:
    load_dotenv()
    from .agent import Agent
    from .graphstore import postgres_saver
    a = Agent(db.connect, checkpointer=postgres_saver(os.environ["DATABASE_URL"]))
    where = "" if "--all" in argv else "and status in ('new', 'failed', 'working')"
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute(f"select id from support.emails where source = 'demo' {where} order by id")]
    print(f"Drafting {len(ids)} demo emails...")
    for n, eid in enumerate(ids, start=1):
        try:
            out = a.start(eid)
            print(f"[{n:>2}/{len(ids)}] email {eid}: {out.get('status')} ({out.get('category')}) {out.get('seconds')}s")
        except Exception as e:
            print(f"[{n:>2}/{len(ids)}] email {eid}: failed ({type(e).__name__}: {e})")
        time.sleep(1.5)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
