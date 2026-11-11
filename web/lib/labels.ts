import type { Step } from "./api";

export const STATUS: Record<string, { label: string; tone: string }> = {
  new: { label: "New", tone: "grey" },
  working: { label: "Working…", tone: "grey" },
  waiting_approval: { label: "Waiting for approval", tone: "blue" },
  needs_human: { label: "Needs a person", tone: "amber" },
  sent: { label: "Sent", tone: "green" },
  rejected: { label: "Rejected", tone: "grey" },
  no_reply: { label: "No reply needed", tone: "grey" },
  failed: { label: "Failed", tone: "red" },
};

export const CATEGORY: Record<string, string> = {
  order_status: "Order status", damaged_or_wrong: "Damaged or wrong item", subscription: "Subscription",
  refund: "Refund", wholesale: "Wholesale", product_question: "Product question", sensitive: "Sensitive", spam: "Spam",
};

const money = (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD" });
const day = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

function shipping(s: any): string {
  if (!s) return "";
  const where = s.carrier ? ` (${s.carrier} ${s.tracking})` : "";
  if (s.status === "in_transit") return `in transit${s.business_days_in_transit ? ` for ${s.business_days_in_transit} business days` : ""}${where}`;
  if (s.status === "delivered") return `delivered${s.delivered_on ? ` ${day(s.delivered_on)}` : ""}${where}`;
  return `${s.status}${where}`;
}

/** One line saying what a lookup found. */
export function summarize(step: Step): string {
  const r = step.result || {};
  if (r.error) return `Error: ${r.error}`;
  switch (step.tool) {
    case "find_customer":
      return r.found ? `Found customer #${r.customer_id}: ${r.name} (${r.city}, ${r.state}), ${r.type}` : "No customer account uses this address";
    case "recent_orders":
      if (!r.found) return "No orders: not a customer";
      return `${r.orders.length} recent order${r.orders.length === 1 ? "" : "s"}` +
        (r.orders[0] ? `; latest #${r.orders[0].order_id} on ${day(r.orders[0].order_date)}, ${shipping(r.orders[0].shipping)}` : "");
    case "order_details":
      return r.found ? `Order #${r.order_id}: ${day(r.order_date)}, ${money(r.items_total)}, ${shipping(r.shipping)}` : r.note;
    case "subscription":
      return r.found ? r.subscriptions.map((s: any) => `${s.plan} (${s.active ? "active" : `cancelled ${day(s.cancelled_on)}`})`).join(", ") : r.note;
    case "policy":
      return `Read the ${r.topic} policy`;
    case "product_info":
      return r.products?.length ? `Found ${r.products.map((p: any) => `${p.name} (${money(p.price)})`).join(", ")}` : "No matching products";
    default:
      return JSON.stringify(r).slice(0, 120);
  }
}

export const TOOL_LABEL: Record<string, string> = {
  find_customer: "Find customer", recent_orders: "Recent orders", order_details: "Order details",
  subscription: "Subscription", policy: "Policy", product_info: "Product info",
};

export function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
