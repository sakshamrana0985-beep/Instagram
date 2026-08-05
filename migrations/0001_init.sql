-- Recall Phase 0 — initial schema (PRD section 10)
create extension if not exists vector;
create extension if not exists pg_trgm;

create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  telegram_id   bigint unique,
  created_at    timestamptz default now(),
  tier          text default 'free',
  weekly_quota  int  default 15,
  timezone      text default 'Asia/Kolkata'
);

create table if not exists items (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references users(id) not null,
  url             text not null,
  url_hash        text not null,           -- global dedupe key
  platform        text,                    -- instagram | youtube | other
  status          text not null default 'pending', -- pending|processing|ready|failed|unsupported

  -- source metadata (attribution is mandatory, see PRD §12)
  creator_handle  text,
  creator_url     text,
  posted_at       timestamptz,
  thumbnail_url   text,
  duration_sec    int,

  -- understanding
  content_type    text,     -- listicle|tutorial|recipe|explainer|news|entertainment
  is_informational boolean,
  is_time_sensitive boolean default false,
  title           text,     -- generated, punchy, widget-safe (<60 chars)
  summary         jsonb,    -- STRUCTURED, shape depends on content_type
  raw_transcript  text,
  topics          text[],   -- ['tax','finance','india'] — powers calendar hooks

  -- retrieval
  embedding       vector(768),

  saved_at        timestamptz default now(),
  last_opened_at  timestamptz,
  open_count      int default 0,
  archived        boolean default false
);

create index if not exists items_embedding_idx on items using ivfflat (embedding vector_cosine_ops);
create index if not exists items_user_saved_idx on items (user_id, saved_at desc);
create unique index if not exists items_user_url_hash_idx on items (user_id, url_hash);
create index if not exists items_title_summary_fts_idx on items
  using gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary::text, '')));

-- global processing cache: one viral reel, processed once
create table if not exists url_cache (
  url_hash     text primary key,
  payload      jsonb,      -- everything except user-specific fields
  processed_at timestamptz default now()
);

-- instrumentation (build plan session 10 depends on these)
create table if not exists search_events (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references users(id) not null,
  query        text not null,
  result_count int not null default 0,
  opened_item  uuid references items(id),
  created_at   timestamptz default now()
);

create table if not exists item_open_events (
  id              uuid primary key default gen_random_uuid(),
  item_id         uuid references items(id) not null,
  user_id         uuid references users(id) not null,
  days_since_saved int not null,
  created_at      timestamptz default now()
);
