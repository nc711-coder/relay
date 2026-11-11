"""Fernwood Coffee Roasters: the same made-up company as Tally (two years of orders, fixed seed).

    from relay.fernwood import generate
    tables = generate()            # {"customers": [row tuples], "products": [...], ...}, columns in COLUMNS

Fernwood sells coffee on its website, by subscription, and wholesale to cafés. The data runs from
2024-11-01 to 2026-10-31 and has patterns worth finding:
  - a holiday spike every November and December (and a HOLIDAY20 discount code)
  - Morning Blend slowly losing share while Ethiopia Yirgacheffe grows
  - the Southwest region growing faster than the others
  - subscribers who cancel, and about 2% of orders refunded

Only Python's `random` module with a fixed seed is used, so the rows are identical on every machine, which is
what keeps the eval set's answer keys fixed.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

START, END = date(2024, 11, 1), date(2026, 10, 31)
TODAY = date(2026, 11, 1)          # the demo's "today": "last quarter" = Q3 2026, "this year" = 2026
SEED = 20261101

COLUMNS = {
    "customers": ["customer_id", "name", "customer_type", "city", "state", "region", "signup_date",
                  "acquisition_channel"],
    "products": ["product_id", "name", "category", "roast", "bag_size_g", "price", "unit_cost", "launched_on"],
    "orders": ["order_id", "customer_id", "order_date", "channel", "discount_code", "status", "shipping_fee"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "line_total"],
    "subscriptions": ["subscription_id", "customer_id", "plan", "monthly_price", "started_on", "cancelled_on"],
    "marketing_spend": ["month", "channel", "spend"],
}

CITIES = {
    "Northeast": [("Boston", "MA"), ("Brooklyn", "NY"), ("Philadelphia", "PA"), ("Portland", "ME"),
                  ("Providence", "RI")],
    "Southeast": [("Atlanta", "GA"), ("Charlotte", "NC"), ("Nashville", "TN"), ("Richmond", "VA"),
                  ("Tampa", "FL")],
    "Midwest": [("Chicago", "IL"), ("Minneapolis", "MN"), ("Columbus", "OH"), ("Madison", "WI"),
                ("Kansas City", "MO")],
    "Southwest": [("Austin", "TX"), ("Phoenix", "AZ"), ("Denver", "CO"), ("Albuquerque", "NM"),
                  ("Tucson", "AZ")],
    "West": [("Seattle", "WA"), ("Portland", "OR"), ("San Diego", "CA"), ("Oakland", "CA"), ("Boise", "ID")],
}
FIRST = ["Ava", "Liam", "Maya", "Noah", "Zoe", "Ethan", "Priya", "Lucas", "Nora", "Omar", "Ivy", "Mateo",
         "Leah", "Kai", "Sofia", "Jonah", "Amara", "Theo", "Hana", "Diego", "Clara", "Ravi", "Elena", "Sam",
         "Grace", "Felix", "Aisha", "Owen", "Mia", "Jasper"]
LAST = ["Nguyen", "Patel", "Garcia", "Kim", "Okafor", "Rossi", "Silva", "Cohen", "Haddad", "Lindqvist",
        "Moreau", "Tanaka", "Brooks", "Reyes", "Novak", "Mensah", "Walsh", "Iyer", "Fischer", "Ortega"]
CAFE_A = ["Copper", "Juniper", "Harbor", "Little", "Northside", "Sparrow", "Oak", "Lantern", "Riverbend",
          "Maple", "Blue Door", "Corner", "Fox", "Granite", "Wild Plum"]
CAFE_B = ["Café", "Coffee House", "Espresso Bar", "Bakery", "Kitchen", "Roastery Bar"]

# name, category, roast, bag grams, price, cost, launched
PRODUCTS = [
    ("Morning Blend", "blend", "medium", 340, 15.00, 5.10, "2022-03-01"),
    ("Morning Blend 1kg", "blend", "medium", 1000, 38.00, 13.90, "2022-03-01"),
    ("Fernwood House Espresso", "blend", "dark", 340, 16.50, 5.40, "2022-03-01"),
    ("Fernwood House Espresso 1kg", "blend", "dark", 1000, 41.00, 14.60, "2022-03-01"),
    ("Night Owl Dark Roast", "blend", "dark", 340, 15.50, 5.00, "2023-01-15"),
    ("Sunrise Breakfast Blend", "blend", "light", 340, 14.50, 4.90, "2023-06-01"),
    ("Ethiopia Yirgacheffe", "single_origin", "light", 340, 19.00, 7.20, "2023-09-01"),
    ("Ethiopia Yirgacheffe 1kg", "single_origin", "light", 1000, 48.00, 19.80, "2023-09-01"),
    ("Colombia Huila", "single_origin", "medium", 340, 17.50, 6.30, "2022-03-01"),
    ("Colombia Huila 1kg", "single_origin", "medium", 1000, 44.00, 17.40, "2022-03-01"),
    ("Guatemala Antigua", "single_origin", "medium", 340, 17.00, 6.10, "2022-08-01"),
    ("Kenya AA", "single_origin", "light", 340, 20.50, 8.10, "2024-02-01"),
    ("Sumatra Mandheling", "single_origin", "dark", 340, 17.50, 6.40, "2022-08-01"),
    ("Brazil Cerrado", "single_origin", "medium", 340, 15.50, 5.30, "2023-03-01"),
    ("Brazil Cerrado 1kg", "single_origin", "medium", 1000, 39.00, 14.20, "2023-03-01"),
    ("Costa Rica Tarrazú", "single_origin", "light", 340, 18.50, 6.90, "2024-05-01"),
    ("Swiss Water Decaf", "decaf", "medium", 340, 16.00, 5.80, "2022-03-01"),
    ("Decaf Espresso", "decaf", "dark", 340, 16.50, 6.00, "2023-11-01"),
    ("Holiday Spice Blend", "blend", "medium", 340, 17.00, 5.60, "2023-11-01"),
    ("Pour-Over Kit", "equipment", None, None, 45.00, 21.00, "2022-03-01"),
    ("Ceramic Dripper", "equipment", None, None, 28.00, 11.50, "2022-03-01"),
    ("Burr Grinder", "equipment", None, None, 129.00, 71.00, "2023-05-01"),
    ("Fernwood Mug", "equipment", None, None, 18.00, 6.20, "2022-03-01"),
    ("Paper Filters (100)", "equipment", None, None, 7.50, 2.10, "2022-03-01"),
]
COFFEE_340 = [i for i, p in enumerate(PRODUCTS) if p[3] == 340]
COFFEE_1KG = [i for i, p in enumerate(PRODUCTS) if p[3] == 1000]
GEAR = [i for i, p in enumerate(PRODUCTS) if p[1] == "equipment"]
PLANS = {"monthly_1_bag": (1, 1, 16.00), "monthly_2_bags": (1, 2, 30.00), "biweekly_1_bag": (2, 1, 31.00)}


def months(start: date, end: date):
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def progress(d: date) -> float:
    """0 at the start of the data, 1 at the end."""
    return (d - START).days / (END - START).days


def season(d: date) -> float:
    return {11: 1.45, 12: 1.9, 1: 0.85, 2: 0.9, 7: 0.9, 8: 0.9}.get(d.month, 1.0)


def product_weight(i: int, d: date) -> float:
    name = PRODUCTS[i][0]
    t = progress(d)
    if name.startswith("Morning Blend"):
        return 3.0 - 2.1 * t                 # the best seller, slowly fading
    if name.startswith("Ethiopia Yirgacheffe"):
        return 0.7 + 2.0 * t                 # the rising star
    if name == "Holiday Spice Blend":
        return 2.5 if d.month in (11, 12) else 0.05
    if name.startswith("Fernwood House Espresso"):
        return 1.8
    return 1.0


def pick_product(rng: random.Random, pool: list[int], d: date) -> int:
    live = [i for i in pool if date.fromisoformat(PRODUCTS[i][6]) <= d]
    return rng.choices(live, weights=[product_weight(i, d) for i in live])[0]


def region_weight(region: str, d: date) -> float:
    return 0.6 + 1.6 * progress(d) if region == "Southwest" else 1.0


def generate(seed: int = SEED) -> dict[str, list[tuple]]:
    rng = random.Random(seed)
    out: dict[str, list[tuple]] = {k: [] for k in COLUMNS}

    out["products"] = [(i + 1, *p[:6], date.fromisoformat(p[6])) for i, p in enumerate(PRODUCTS)]

    # ---- customers: retail people signing up over time, and wholesale cafés
    regions = list(CITIES)
    signup_days = (END - date(2024, 6, 1)).days
    customers = []                          # (id, type, region, signup)
    for cid in range(1, 4001):
        wholesale = cid % 33 == 0           # about 120 cafés
        while True:                          # Southwest sign-ups lean later in the data
            signup = date(2024, 6, 1) + timedelta(days=int(signup_days * rng.random() ** 0.85))
            region = rng.choice(regions)
            if rng.random() < region_weight(region, signup) / 2.2:
                break
        city, state = rng.choice(CITIES[region])
        if wholesale:
            name = f"{rng.choice(CAFE_A)} {rng.choice(CAFE_B)}"
            ctype, acq = "wholesale", "wholesale_sales"
        else:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            ctype = "retail"
            acq = rng.choices(["organic", "paid_search", "social", "referral"], [40, 25, 20, 15])[0]
        out["customers"].append((cid, name, ctype, city, state, region, signup, acq))
        customers.append((cid, ctype, region, signup))
    retail = [c for c in customers if c[1] == "retail"]
    cafes = [c for c in customers if c[1] == "wholesale"]

    orders, items = out["orders"], out["order_items"]
    order_id = [0]
    item_id = [0]

    def add_order(cid, d, channel, lines, discount=None, ship=0.0):
        order_id[0] += 1
        status = "refunded" if rng.random() < 0.02 else "completed"
        orders.append((order_id[0], cid, d, channel, discount, status, ship))
        off = {"WELCOME10": 0.10, "HOLIDAY20": 0.20}.get(discount, 0.0)
        for pid, qty, unit in lines:
            item_id[0] += 1
            price = round(unit * (1 - off), 2)
            items.append((item_id[0], order_id[0], pid + 1, qty, price, round(price * qty, 2)))

    # ---- subscriptions and their orders
    subs = rng.sample(retail, 1200)
    for sid, (cid, _, _, signup) in enumerate(sorted(subs, key=lambda c: c[0]), start=1):
        plan = rng.choices(list(PLANS), [55, 25, 20])[0]
        per_month, bags, price = PLANS[plan]
        started = max(signup + timedelta(days=rng.randint(0, 60)), START - timedelta(days=rng.randint(0, 120)))
        if started > END:
            started = END - timedelta(days=rng.randint(0, 30))
        cancelled = None
        d = started
        while d <= END:
            if d >= START:
                for k in range(per_month):
                    od = d + timedelta(days=14 * k)
                    if od <= END:
                        pid = pick_product(rng, COFFEE_340, od)
                        add_order(cid, od, "subscription", [(pid, bags, price / bags / per_month)])
            d = date(d.year + (d.month == 12), d.month % 12 + 1, min(d.day, 28))
            if rng.random() < 0.045 and d <= END:     # about 4.5% cancel each month
                cancelled = d
                break
        out["subscriptions"].append((sid, cid, plan, price, started, cancelled))

    # ---- wholesale: each café orders 1kg bags every one to three weeks
    for cid, _, region, signup in cafes:
        d = max(signup, START) + timedelta(days=rng.randint(0, 20))
        while d <= END:
            lines = []
            for pid in {pick_product(rng, COFFEE_1KG, d) for _ in range(rng.randint(1, 3))}:
                lines.append((pid, rng.randint(2, 8), round(PRODUCTS[pid][4] * 0.7, 2)))
            add_order(cid, d, "wholesale", lines)
            d += timedelta(days=rng.choice([7, 14, 14, 21]))

    # ---- web orders: day by day, growing over time, peaking at the holidays
    first_order: set[int] = set()
    d = START
    while d <= END:
        expected = (12 + 10 * progress(d)) * season(d)
        n = max(0, int(rng.gauss(expected, expected ** 0.5)))
        eligible = [c for c in retail if c[3] <= d]
        weights = [region_weight(c[2], d) for c in eligible]
        for cid, _, _, _ in rng.choices(eligible, weights=weights, k=n):
            lines = {}
            for _ in range(rng.choices([1, 2, 3], [60, 30, 10])[0]):
                pid = pick_product(rng, GEAR, d) if rng.random() < 0.15 else pick_product(rng, COFFEE_340, d)
                lines[pid] = lines.get(pid, 0) + rng.choices([1, 2], [80, 20])[0]
            lines = [(pid, q, PRODUCTS[pid][4]) for pid, q in lines.items()]
            discount = None
            if cid not in first_order:
                discount = "WELCOME10"
            elif (d.month == 11 and d.day >= 20 or d.month == 12) and rng.random() < 0.35:
                discount = "HOLIDAY20"
            first_order.add(cid)
            subtotal = sum(q * p for _, q, p in lines)
            add_order(cid, d, "web", lines, discount, 0.0 if subtotal >= 40 else 5.99)
        d += timedelta(days=1)

    # ---- orders in date order, renumbered so order_id rises with the date
    order_rows = sorted(orders, key=lambda o: (o[2], o[0]))
    new_id = {o[0]: i for i, o in enumerate(order_rows, start=1)}
    out["orders"] = [(new_id[o[0]], *o[1:]) for o in order_rows]
    out["order_items"] = sorted(((i[0], new_id[i[1]], *i[2:]) for i in items), key=lambda r: (r[1], r[0]))
    out["order_items"] = [(n, *r[1:]) for n, r in enumerate(out["order_items"], start=1)]

    # ---- marketing spend per month and channel
    for m in months(START, END):
        t = progress(m)
        for ch, base in [("paid_search", 4200), ("social", 2600), ("email", 600), ("events", 900)]:
            amount = base * (1 + 0.5 * t) * (1.6 if m.month in (11, 12) and ch != "events" else 1.0)
            if ch == "events" and m.month not in (3, 4, 9, 10):
                amount *= 0.2
            out["marketing_spend"].append((m, ch, round(amount * (0.9 + 0.2 * rng.random()), 2)))
    return out


if __name__ == "__main__":
    for name, rows in generate().items():
        print(f"{name:16} {len(rows):>7,} rows")
