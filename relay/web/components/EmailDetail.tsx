"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Email } from "@/lib/api";
import { CATEGORY, STATUS, summarize, TOOL_LABEL, when } from "@/lib/labels";

export default function EmailDetail({ email, onChange, onBack }: {
  email: Email; onChange: (e: Email) => void; onBack: () => void;
}) {
  const [text, setText] = useState(email.reply || "");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setText(email.reply || ""); setError(""); }, [email.id, email.reply]);

  const waiting = email.status === "waiting_approval" || email.status === "needs_human";
  const editable = waiting && email.mine;
  const edited = text.trim() !== (email.reply || "").trim();
  const status = STATUS[email.status] || { label: email.status, tone: "grey" };

  async function decide(kind: "approved" | "edited" | "rejected") {
    setBusy(kind); setError("");
    try {
      onChange(await api.decide(email.id, kind, kind === "edited" ? text : undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy("");
    }
  }

  return (
    <article className="detail">
      <button className="back" onClick={onBack}>← Inbox</button>

      <header className="detail-head">
        <h2>{email.subject}</h2>
        <p className="from"><strong>{email.from_name || email.from_addr}</strong> &lt;{email.from_addr}&gt; · {when(email.received_at)}</p>
        <div className="tags">
          <span className={`pill ${status.tone}`}>{status.label}</span>
          {email.category && <span className="tag">{CATEGORY[email.category] || email.category}</span>}
          {email.urgency === "high" && <span className="tag urgent">Urgent</span>}
          {email.mine && <span className="tag">Your test email</span>}
        </div>
      </header>

      <section className="original"><pre>{email.body}</pre></section>

      {email.status === "no_reply" && <div className="note-box">Sorted as spam: no reply drafted, nothing sent.</div>}

      {email.reply !== null && email.status !== "no_reply" && (
        <section className="agent">
          <h3>The agent&apos;s draft</h3>

          {!!email.reasons?.length && (
            <div className="flag">
              <strong>Needs a person:</strong>
              <ul>{email.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}

          {email.status === "sent" ? (
            <div className="sent">
              <p className="sent-label">{email.decision === "edited" ? "Edited and sent" : "Approved and sent"}</p>
              <pre>{email.final_reply}</pre>
            </div>
          ) : email.status === "rejected" ? (
            <div className="sent rejected"><p className="sent-label">Rejected: nothing was sent.</p><pre>{email.reply}</pre></div>
          ) : (
            <>
              <textarea value={text} onChange={(e) => setText(e.target.value)} readOnly={!editable} rows={9} aria-label="Draft reply" />
              {editable ? (
                <div className="actions">
                  <button className="primary" disabled={!!busy || !text.trim()} onClick={() => decide(edited ? "edited" : "approved")}>
                    {busy === "approved" || busy === "edited" ? "Sending…" : edited ? "Send my edited reply" : "Approve and send"}
                  </button>
                  <button className="secondary" disabled={!!busy} onClick={() => decide("rejected")}>
                    {busy === "rejected" ? "Rejecting…" : "Reject"}
                  </button>
                </div>
              ) : waiting ? (
                <p className="hint">Demo emails are read-only. <strong>Send your own test email</strong> to approve, edit or reject a draft.</p>
              ) : null}
              {error && <p className="error">{error}</p>}
            </>
          )}

          {email.ticket?.title && (
            <div className="ticket">
              <span className="ticket-label">Ticket</span>
              <span>{email.ticket.title}</span>
              {email.ticket.action && <span className="ticket-action">To do: {email.ticket.action}</span>}
            </div>
          )}

          {!!email.steps?.length && (
            <details className="steps" open>
              <summary>What the agent looked up ({email.steps.length})</summary>
              <ol>
                {email.steps.map((s, i) => (
                  <li key={i}>
                    <span className="tool">{TOOL_LABEL[s.tool] || s.tool}</span>
                    <span>{summarize(s)}</span>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {!!email.checks?.rewrites && (
            <p className="hint">The first draft had a fact that didn&apos;t match the records, so the agent rewrote it.</p>
          )}
          {email.seconds && <p className="meta">Drafted in {email.seconds.toFixed(1)}s</p>}
        </section>
      )}
    </article>
  );
}
