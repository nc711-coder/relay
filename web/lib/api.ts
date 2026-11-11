export type Step = { tool: string; args: Record<string, unknown>; result: any };

export type EmailSummary = {
  id: number; code: string | null; received_at: string; from_name: string; from_addr: string; subject: string;
  snippet: string; source: "demo" | "form" | "gmail"; status: string; category: string | null;
  urgency: string | null; needs_human: boolean | null;
};

export type Email = EmailSummary & {
  body: string; reply: string | null; ticket: { title?: string; priority?: string; action?: string; refund_amount?: number } | null;
  reasons: string[] | null; checks: { problems?: string[]; rewrites?: number; flags?: string[] } | null;
  steps: Step[] | null; decision: string | null; final_reply: string | null; decided_at: string | null;
  mine: boolean; seconds?: number;
};

export type Persona = { id: string; name: string; email: string; hint: string };
export type Card = { email_id: number; title: string; from: string; category: string; action: string; priority: string };
export type Board = { waiting: Card[]; person: Card[]; open: Card[]; done: Card[] };

export const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function visitor(): string {
  try {
    let v = localStorage.getItem("relay-visitor");
    if (!v) {
      v = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9-]/g, "");
      localStorage.setItem("relay-visitor", v);
    }
    return v;
  } catch {
    return "visitor-session-" + Math.floor(Date.now() / 1000);
  }
}

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Visitor": visitor(), ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError("Couldn't reach Relay's server. It may be waking up; try again in a few seconds.");
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError((data && data.detail) || `The server answered with an error (${r.status}).`);
  return data as T;
}

export const api = {
  emails: () => call<{ emails: EmailSummary[] }>("/api/emails").then((d) => d.emails),
  email: (id: number) => call<Email>(`/api/emails/${id}`),
  personas: () => call<{ personas: Persona[] }>("/api/personas").then((d) => d.personas),
  send: (body: { persona: string; from_name?: string; subject: string; body: string }) =>
    call<Email>("/api/emails", { method: "POST", body: JSON.stringify(body) }),
  decide: (id: number, decision: "approved" | "edited" | "rejected", reply?: string) =>
    call<Email>(`/api/emails/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, reply }) }),
  board: () => call<Board>("/api/board"),
};
