"use client";

import type { Board } from "@/lib/api";
import { CATEGORY } from "@/lib/labels";

const COLUMNS: [keyof Board, string, string][] = [
  ["waiting", "Waiting for approval", "Drafts ready to approve"],
  ["person", "Needs a person", "Flagged by the agent's rules"],
  ["open", "Open", "Sent, with something left to do"],
  ["done", "Done", "Sent and finished"],
];

export default function BoardView({ board, onOpen }: { board: Board; onOpen: (id: number) => void }) {
  return (
    <div className="board">
      {COLUMNS.map(([key, title, sub]) => (
        <section key={key} className="column">
          <h3>{title} <span className="count">{board[key].length}</span></h3>
          <p className="hint small">{sub}</p>
          {board[key].map((c) => (
            <button key={c.email_id} className={`card-item ${c.priority}`} onClick={() => onOpen(c.email_id)}>
              <span className="card-title">{c.title}</span>
              <span className="card-meta">{c.from} · {CATEGORY[c.category] || c.category}</span>
              {c.action && <span className="card-action">{c.action}</span>}
            </button>
          ))}
          {!board[key].length && <p className="empty">Nothing here.</p>}
        </section>
      ))}
    </div>
  );
}
