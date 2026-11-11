"""Where the agent's paused graphs are saved: Postgres, in their own "relay_graph" schema.

LangGraph's checkpointer writes a snapshot after every step, so a draft waiting for approval survives
restarts and new deploys: approving it hours later resumes the graph from exactly where it stopped.
"""
from __future__ import annotations

from psycopg.rows import dict_row

SCHEMA = "relay_graph"


def postgres_saver(url: str):
    """A PostgresSaver backed by a small connection pool (each connection uses the relay_graph schema)."""
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as c:
        c.execute(f"create schema if not exists {SCHEMA}")

    def configure(conn):
        conn.execute(f"set search_path to {SCHEMA}")

    pool = ConnectionPool(url, min_size=1, max_size=4, open=True, configure=configure, check=ConnectionPool.check_connection,
                          kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None})
    saver = PostgresSaver(pool)
    saver.setup()
    return saver
