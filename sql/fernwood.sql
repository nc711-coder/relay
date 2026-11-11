-- Fernwood Coffee Roasters: the demo database Tally answers questions about.
-- Its own schema, so it sits beside other projects in the same Supabase database without touching them.
drop schema if exists fernwood cascade;
create schema fernwood;

create table fernwood.customers (
    customer_id          integer primary key,
    name                 text not null,
    customer_type        text not null check (customer_type in ('retail', 'wholesale')),
    city                 text not null,
    state                text not null,
    region               text not null,
    signup_date          date not null,
    acquisition_channel  text not null
);

create table fernwood.products (
    product_id   integer primary key,
    name         text not null unique,
    category     text not null check (category in ('blend', 'single_origin', 'decaf', 'equipment')),
    roast        text check (roast in ('light', 'medium', 'dark')),
    bag_size_g   integer,
    price        numeric(8, 2) not null,
    unit_cost    numeric(8, 2) not null,
    launched_on  date not null
);

create table fernwood.orders (
    order_id       integer primary key,
    customer_id    integer not null references fernwood.customers,
    order_date     date not null,
    channel        text not null check (channel in ('web', 'subscription', 'wholesale')),
    discount_code  text,
    status         text not null check (status in ('completed', 'refunded')),
    shipping_fee   numeric(8, 2) not null default 0
);

create table fernwood.order_items (
    order_item_id  integer primary key,
    order_id       integer not null references fernwood.orders,
    product_id     integer not null references fernwood.products,
    quantity       integer not null check (quantity > 0),
    unit_price     numeric(8, 2) not null,
    line_total     numeric(10, 2) not null
);

create table fernwood.subscriptions (
    subscription_id  integer primary key,
    customer_id      integer not null references fernwood.customers,
    plan             text not null,
    monthly_price    numeric(8, 2) not null,
    started_on       date not null,
    cancelled_on     date
);

create table fernwood.marketing_spend (
    month    date not null,
    channel  text not null,
    spend    numeric(10, 2) not null,
    primary key (month, channel)
);

create index on fernwood.orders (order_date);
create index on fernwood.orders (customer_id);
create index on fernwood.order_items (order_id);
create index on fernwood.order_items (product_id);
