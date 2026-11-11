"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, type Email, type Persona } from "@/lib/api";

const IDEAS: Record<string, string> = {
  default: "Where is my order? It's been a while.",
  "Has an active coffee subscription": "Can I pause my subscription for a month?",
  "Recent order delivered (try a damaged bag)": "My last bag arrived ripped open. What can you do?",
  "A café with wholesale orders": "Can we switch our deliveries to every two weeks?",
  "Recently received an order": "I don't love the coffee I got. Can I return it?",
  "Not a customer yet": "Do you ship to Canada?",
};

export default function SendForm({ onClose, onSent }: { onClose: () => void; onSent: (e: Email) => void }) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.personas().then((p) => { setPersonas(p); if (p[0]) { setPersona(p[0].id); setBody(IDEAS[p[0].hint] || IDEAS.default); } })
      .catch((e) => setError(e.message));
  }, []);

  function pick(id: string) {
    setPersona(id);
    const p = personas.find((x) => x.id === id);
    setBody(IDEAS[p?.hint || ""] || IDEAS.default);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      onSent(await api.send({ persona, subject: subject || "Question", body }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  const chosen = personas.find((p) => p.id === persona);
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label="Send a test email">
      <form className="modal" onSubmit={submit}>
        <h2>Send a test email</h2>
        <p className="hint">Write as one of Fernwood&apos;s customers. The agent looks up their real (fictional) orders and drafts a reply for you to approve.</p>
        <label>From
          <select value={persona} onChange={(e) => pick(e.target.value)} disabled={busy}>
            {personas.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.hint}</option>)}
          </select>
        </label>
        {chosen?.email && <p className="hint small">{chosen.email}</p>}
        <label>Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={150} placeholder="Question" disabled={busy} /></label>
        <label>Message<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} maxLength={3000} disabled={busy} required /></label>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="primary" type="submit" disabled={busy || body.trim().length < 3}>
            {busy ? "The agent is reading, looking things up and drafting…" : "Send to the agent"}
          </button>
          <button className="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
