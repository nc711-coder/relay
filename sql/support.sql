-- Relay's own tables, in a "support" schema beside Fernwood's data (the "fernwood" schema, shared with Tally).
drop schema if exists support cascade;
create schema support;

create table support.customer_emails (
    customer_id  integer primary key references fernwood.customers,
    email        text not null unique
);

create table support.shipments (
    order_id            integer primary key references fernwood.orders,
    carrier             text not null,
    tracking            text not null,
    status              text not null check (status in ('processing', 'in_transit', 'delivered', 'cancelled')),
    shipped_on          date,
    delivered_on        date,
    estimated_delivery  date
);

create table support.emails (
    id           serial primary key,
    code         text unique,                     -- e01... for the built-in demo emails
    received_at  timestamptz not null default now(),
    from_addr    text not null,
    from_name    text not null default '',
    subject      text not null default '',
    body         text not null,
    source       text not null default 'form' check (source in ('demo', 'form', 'gmail')),
    external_id  text unique,                     -- Gmail's message id
    visitor      text,                            -- who sent it from the demo form (for rate limits)
    status       text not null default 'new'
                 check (status in ('new', 'working', 'waiting_approval', 'needs_human', 'sent', 'rejected', 'no_reply', 'failed')),
    category     text,
    urgency      text,
    thread_id    text                             -- the agent's LangGraph thread
);
create index on support.emails (received_at desc);

create table support.drafts (
    email_id     integer primary key references support.emails on delete cascade,
    reply        text not null default '',
    ticket       jsonb not null default '{}',
    needs_human  boolean not null default false,
    reasons      jsonb not null default '[]',
    checks       jsonb not null default '{}',
    steps        jsonb not null default '[]',     -- every tool call and what it returned
    created_at   timestamptz not null default now(),
    decision     text check (decision in ('approved', 'edited', 'rejected')),
    final_reply  text,
    decided_at   timestamptz
);

create table support.tickets (
    id          serial primary key,
    email_id    integer not null references support.emails on delete cascade,
    title       text not null,
    category    text not null,
    priority    text not null default 'normal' check (priority in ('low', 'normal', 'high')),
    action      text not null default '',
    status      text not null default 'open' check (status in ('open', 'waiting_on_customer', 'done')),
    created_at  timestamptz not null default now()
);
