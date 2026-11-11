"use client";

import { useCallback, useEffect, useState } from "react";
import BoardView from "@/components/BoardView";
import EmailDetail from "@/components/EmailDetail";
import SendForm from "@/components/SendForm";
import { api, type Board, type Email, type EmailSummary } from "@/lib/api";
import { CATEGORY, STATUS, when } from "@/lib/labels";

const REPO = "https://github.com/nc711-coder/relay";
type Filter = "all" | "waiting_approval" | "needs_human" | "sent";

export default function Home() {
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [open, setOpen] = useState<Email | null>(null);
  const [view, setView] = useState<"inbox" | "board">("inbox");
  const [board, setBoard] = useState<Board | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");

  const refresh = useCallback(async () => {
    try {
      setEmails(await api.emails(searched));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [searched]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {                                   // search a moment after typing stops
    const t = setTimeout(() => setSearched(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => { if (view === "board") api.board().then(setBoard).catch((e) => setError(e.message)); }, [view, emails]);

  async function show(id: number) {
    try {
      setOpen(await api.email(id));
      setView("inbox");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function updated(e: Email) {
    setOpen(e);
    refresh();
  }

  function deleted() {
    setOpen(null);
    refresh();
  }

  const shown = emails.filter((e) => filter === "all" || e.status === filter);
  const count = (s: string) => emails.filter((e) => e.status === s).length;

  return (
    <main className="app">
      <header className="top">
        <div className="brand"><span className="logo" aria-hidden="true">↻</span><span className="wordmark">Relay</span>
          <span className="sub">AI support agent for Fernwood Coffee (fictional)</span></div>
        <nav>
          <button className={view === "inbox" ? "on" : ""} onClick={() => setView("inbox")}>Inbox</button>
          <button className={view === "board" ? "on" : ""} onClick={() => setView("board")}>Tickets</button>
          <button className="primary" onClick={() => setSending(true)}>Send a test email</button>
        </nav>
      </header>

      <p className="lede">
        The agent reads each email, looks up the customer&apos;s orders and policies with tools, and drafts a reply.
        Code checks every fact, and <strong>nothing is sent until a person approves it.</strong>
      </p>
      {error && <p className="error banner">{error}</p>}

      {view === "board" ? (
        board ? <BoardView board={board} onOpen={show} /> : <p className="hint">Loading…</p>
      ) : (
        <div className={`split ${open ? "has-open" : ""}`}>
          <aside className="list">
            <div className="list-head">
            <div className="search">
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name, company, order or text" aria-label="Search emails" />
              {query && <button onClick={() => setQuery("")} aria-label="Clear search">✕</button>}
            </div>
            <div className="filters">
              {([["all", `All ${emails.length}`], ["waiting_approval", `To approve ${count("waiting_approval")}`],
                 ["needs_human", `Needs a person ${count("needs_human")}`], ["sent", `Sent ${count("sent")}`]] as [Filter, string][]).map(([k, label]) => (
                <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{label}</button>
              ))}
            </div>
            </div>
            {shown.map((e) => {
              const s = STATUS[e.status] || { label: e.status, tone: "grey" };
              return (
                <button key={e.id} className={`row ${open?.id === e.id ? "selected" : ""}`} onClick={() => show(e.id)}>
                  <span className="row-top"><span className="who">{e.from_name || e.from_addr}</span><span className="time">{when(e.received_at)}</span></span>
                  <span className="subject">{e.subject}</span>
                  <span className="snippet">{e.snippet}</span>
                  <span className="row-tags">
                    <span className={`pill ${s.tone}`}>{s.label}</span>
                    {e.category && <span className="tag">{CATEGORY[e.category] || e.category}</span>}
                    {e.source === "form" && <span className="tag">Yours</span>}
                  </span>
                </button>
              );
            })}
            {!shown.length && <p className="empty">{searched ? <>No emails match &ldquo;{searched}&rdquo;.</> : "No emails here."}</p>}
          </aside>
          <section className="pane">
            {open ? <EmailDetail email={open} onChange={updated} onBack={() => setOpen(null)} onDeleted={deleted} />
              : <div className="placeholder"><p>Pick an email to see the agent&apos;s draft and every lookup it made.</p>
                  <button className="primary" onClick={() => setSending(true)}>Or send your own test email</button></div>}
          </section>
        </div>
      )}

      <footer className="foot">
        <p>Built with LangGraph. The agent&apos;s tools can only see the sender&apos;s own records; refunds over $50,
          legal threats and instructions hidden in emails always go to a person.</p>
        <p><a href={REPO}>Source code on GitHub</a> · Fictional company and customers.</p>
      </footer>

      {sending && <SendForm onClose={() => setSending(false)} onSent={(e) => { setSending(false); setOpen(e); setView("inbox"); refresh(); }} />}
    </main>
  );
}
