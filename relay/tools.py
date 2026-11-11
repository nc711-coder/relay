"""The agent's lookups. Every one is tied to the email's sender: it can only see that person's records.

    tools = Tools(conn, sender="ava.nguyen12@example.com")
    tools.call("recent_orders", {"limit": 3})     # -> JSON-able dict; every call is kept in tools.log

The AI picks which tool to call and with what arguments, but it can't choose whose data to read: the
customer is fixed by the From address before the agent starts. Asking for an order that belongs to someone
else returns "not found", exactly as if it didn't exist, so nothing leaks.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .fernwood import TODAY
from .support_data import business_days

POLICIES = Path(__file__).with_name("policies.md").read_text(encoding="utf-8")
TOPICS = re.findall(r"^## (\w[\w ]*)$", POLICIES, re.M)

SPECS = [
    {"type": "function", "function": {
        "name": "find_customer", "description": "Look up the customer who sent this email (by their email address).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "recent_orders",
        "description": "The sender's most recent orders, newest first, with items, totals and shipping status.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "order_details", "description": "One of the sender's orders by its order number.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "integer"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {
        "name": "subscription", "description": "The sender's coffee subscriptions (active and cancelled).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "policy", "description": "Fernwood's support policy on one topic.",
        "parameters": {"type": "object", "properties": {"topic": {"type": "string", "enum": TOPICS}},
                       "required": ["topic"]}}},
    {"type": "function", "function": {
        "name": "product_info", "description": "Products whose name contains the given words: price, roast, size.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
]
NAMES = [s["function"]["name"] for s in SPECS]


def _d(v):
    return v.isoformat() if isinstance(v, date) else v


class Tools:
    def __init__(self, conn, sender: str):
        self.conn = conn
        self.sender = sender.strip().lower()
        self.log: list[dict] = []
        row = conn.execute("""select c.customer_id, c.name, c.customer_type, c.city, c.state, c.signup_date
                              from support.customer_emails e join fernwood.customers c using (customer_id)
                              where lower(e.email) = %s""", (self.sender,)).fetchone()
        self.customer = dict(zip(["customer_id", "name", "customer_type", "city", "state", "signup_date"], row)) if row else None

    # ---- dispatch -----------------------------------------------------------------------------------
    def call(self, name: str, args: dict | None) -> dict:
        args = args or {}
        if name not in NAMES:
            result = {"error": f"there is no tool called {name}"}
        else:
            try:
                result = getattr(self, name)(**args)
            except TypeError as e:
                result = {"error": f"bad arguments for {name}: {e}"}
        self.log.append({"tool": name, "args": args, "result": result})
        return result

    # ---- tools --------------------------------------------------------------------------------------
    def find_customer(self) -> dict:
        if not self.customer:
            return {"found": False, "note": "No customer account uses this email address."}
        c = self.customer
        return {"found": True, "customer_id": c["customer_id"], "name": c["name"], "type": c["customer_type"],
                "city": c["city"], "state": c["state"], "customer_since": _d(c["signup_date"])}

    def _order(self, oid: int) -> dict:
        o = self.conn.execute("""select o.order_id, o.order_date, o.channel, o.status, o.discount_code, o.shipping_fee
                                 from fernwood.orders o where o.order_id = %s and o.customer_id = %s""",
                              (oid, self.customer["customer_id"])).fetchone()
        items = self.conn.execute("""select p.name, i.quantity, i.unit_price, i.line_total from fernwood.order_items i
                                     join fernwood.products p using (product_id) where i.order_id = %s
                                     order by i.order_item_id""", (oid,)).fetchall()
        s = self.conn.execute("""select carrier, tracking, status, shipped_on, delivered_on, estimated_delivery
                                 from support.shipments where order_id = %s""", (oid,)).fetchone()
        out = {"order_id": o[0], "order_date": _d(o[1]), "channel": o[2],
               "payment_status": "refunded" if o[3] == "refunded" else "paid", "discount_code": o[4],
               "items": [{"product": n, "quantity": q, "unit_price": float(u), "line_total": float(t)} for n, q, u, t in items],
               "items_total": round(sum(float(t) for *_, t in items), 2), "shipping_fee": float(o[5])}
        if s:
            ship = dict(zip(["carrier", "tracking", "status", "shipped_on", "delivered_on", "estimated_delivery"], map(_d, s)))
            if s[4]:
                ship["days_since_delivery"] = (TODAY - s[4]).days
            if s[2] == "in_transit" and s[3]:
                ship["business_days_in_transit"] = business_days(s[3], TODAY)
            out["shipping"] = ship
        else:
            out["shipping"] = {"status": "delivered", "note": "shipping records before August 2026 are archived"}
        return out

    def recent_orders(self, limit: int = 5) -> dict:
        if not self.customer:
            return {"found": False, "note": "No customer account uses this email address, so there are no orders to show."}
        limit = max(1, min(int(limit or 5), 10))
        ids = [r[0] for r in self.conn.execute("""select order_id from fernwood.orders where customer_id = %s
                                                   order by order_date desc, order_id desc limit %s""",
                                                (self.customer["customer_id"], limit))]
        return {"found": True, "today": TODAY.isoformat(), "orders": [self._order(i) for i in ids]}

    def order_details(self, order_id) -> dict:
        try:
            oid = int(str(order_id).lstrip("#").strip())
        except ValueError:
            return {"found": False, "note": f"'{order_id}' isn't an order number."}
        if not self.customer:
            return {"found": False, "note": "No customer account uses this email address."}
        owned = self.conn.execute("select 1 from fernwood.orders where order_id = %s and customer_id = %s",
                                  (oid, self.customer["customer_id"])).fetchone()
        if not owned:   # also when it exists but belongs to someone else: never reveal which
            return {"found": False, "note": f"No order #{oid} belongs to this customer."}
        return {"found": True, "today": TODAY.isoformat(), **self._order(oid)}

    def subscription(self) -> dict:
        if not self.customer:
            return {"found": False, "note": "No customer account uses this email address."}
        rows = self.conn.execute("""select subscription_id, plan, monthly_price, started_on, cancelled_on
                                    from support.customer_emails e join fernwood.subscriptions s using (customer_id)
                                    where e.customer_id = %s order by started_on""", (self.customer["customer_id"],)).fetchall()
        subs = [{"subscription_id": r[0], "plan": r[1], "monthly_price": float(r[2]), "started_on": _d(r[3]),
                 "cancelled_on": _d(r[4]), "active": r[4] is None} for r in rows]
        return {"found": bool(subs), "subscriptions": subs,
                **({} if subs else {"note": "This customer has no subscription, active or cancelled."})}

    def policy(self, topic: str) -> dict:
        topic = str(topic).lower().strip()
        m = re.search(rf"^## {re.escape(topic)}\n(.*?)(?=^## |\Z)", POLICIES, re.M | re.S)
        if not m:
            return {"error": f"no policy called '{topic}'. Topics: {', '.join(TOPICS)}"}
        return {"topic": topic, "text": m.group(1).strip()}

    def product_info(self, name: str) -> dict:
        skip = {"the", "a", "an", "of", "your", "price", "cost", "how", "much", "is", "do", "you", "sell", "bag", "bags"}
        words = [w for w in re.findall(r"[\w']+", str(name).lower()) if len(w) > 1 and w not in skip][:4]
        if not words:
            return {"products": []}
        sql = """select name, category, roast, bag_size_g, price from fernwood.products where {} order by name limit 6"""
        rows = self.conn.execute(sql.format(" and ".join(["lower(name) like %s"] * len(words))),
                                 [f"%{w}%" for w in words]).fetchall()
        if not rows:                         # no product has every word: any product with one of them
            rows = self.conn.execute(sql.format(" or ".join(["lower(name) like %s"] * len(words))),
                                     [f"%{w}%" for w in words]).fetchall()
        return {"products": [{"name": n, "category": c, "roast": r, "bag_size_g": b, "price": float(p)}
                             for n, c, r, b, p in rows]}
