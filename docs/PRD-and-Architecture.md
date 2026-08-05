# Recall — PRD & Technical Architecture

*(working name — swap freely)*

**Version:** 0.1 — planning draft
**Status:** pre-build
**Target budget for Phase 0–2:** under $50 total

---

## 1. One-line description

You save things on Instagram and never look at them again. We turn those videos into notes you can search — and bring them back when you need them.

---

## 2. The problem

A person sees a reel with real information in it — five tax-saving hacks, a list of AI tools, a workout form correction. They're distracted, on a bus, half-watching. They tap Instagram's bookmark icon as a promise to themselves.

They never return. A year later that folder holds 400 identical-looking thumbnails. The information is locked inside video, so it can't be searched, skimmed, or remembered. The save felt productive and produced nothing.

**Three failures compound:**

| Failure | Cause |
|---|---|
| Can't find it | Video isn't text, so nothing indexes it |
| Can't skim it | Retrieving one fact costs 45 seconds of rewatching |
| Never returns | Saving is passive — nothing ever brings it back |

Most tools in this space fix only the first. The product wins by fixing all three.

---

## 3. Product thesis

> Summarization is the machinery. **Retrieval and resurfacing are the product.**

Anything can summarize a video. What almost nothing does: hand you the thing you forgot you saved, at the exact moment it matters. The tax reel should reappear in March, not sit in a prettier graveyard.

**Design principle for every feature decision:**
*Does this increase the chance the user gets value from something they saved three months ago?*

---

## 4. Target user (v1)

**Primary:** 20–35, learns from short-form video, saves heavily, retrieves nothing. Already frustrated with their own Saved folder.

**Vertical focus for launch: knowledge/skills content** — finance & tax, AI/tech tools, career, study, productivity.

Rationale:
- Recipe and travel verticals are crowded by funded competitors
- Knowledge content has the strongest "I need this months later" retrieval moment
- Overlaps heavily with early-adopter behaviour (they'll try new apps)
- Strong calendar hooks for resurfacing (tax season, appraisal cycle, exam season)

**Explicitly not v1:** creators doing competitive research, teams, agencies. Different product.

---

## 5. Scope

### In scope for v1

- Share-sheet capture from Instagram + YouTube (Android first)
- Accepts *any* link — unsupported platforms save as link-only with "summary coming soon"
- Auto content-type classification
- Structured summary using per-type templates
- Semantic search across the library
- Weekly digest notification
- Single-card home-screen widget
- Free tier with a hard cap

### Out of scope for v1

| Excluded | Why |
|---|---|
| Server-side video storage | Copyright exposure — see §12 |
| Instagram login / importing existing Saved folder | Puts you inside Meta ToS; loses legal footing |
| TikTok | Adds a fourth brittle pipeline before product-market fit |
| Collections, folders, tags | Search should make these unnecessary; add only if users demand |
| Social features, sharing libraries | Distraction |
| iOS | Ship after Android proves the loop (see §7) |

---

## 6. Phase plan

### Phase 0 — Validation (2 weeks, ~$0)

**A Telegram bot. No app.**

User forwards a link → bot replies with a structured summary → `/search <query>` retrieves from their history.

Why this first: no app store review, no share-sheet engineering, no store fees, no rejection risk. Working product in days instead of months.

**Ship to 50 people.** Recruit from Reddit (r/india, r/developersIndia), Twitter, WhatsApp groups.

**The metric that matters is not "do they like it."** Everyone will say it's cool. The metric is:

> **Does anyone run `/search` in week 2+?**

- If ≥25% of users search at least once after their first week → the thesis holds, build the app.
- If nobody searches → the retrieval premise is wrong. Pivot before spending four months.

Secondary data you get free: which platforms people actually forward (tells you whether TikTok matters), and what content types dominate (tunes your templates).

### Phase 1 — Android app (6–8 weeks, ~$25)

Share-sheet capture, library, search, digest. Only cost is the one-time Google Play developer fee.

### Phase 2 — Retention layer (3–4 weeks, ~$0)

Widget, calendar-aware resurfacing, refined ranking.

### Phase 3 — Expand (as warranted)

TikTok, iOS ($99/yr Apple fee), paid tier.

---

## 7. Why Android first

- Play developer fee is **$25 one-time** vs Apple's **$99/year**
- Android share-sheet integration is a simple `intent-filter`; iOS needs a Share Extension with a separate app target and memory constraints
- Home-screen widgets are far less restricted (see §11)
- India-heavy early user base skews Android

Trade-off: iOS users spend more. Revisit at Phase 3.

---

## 8. Zero-cost stack

Everything below has a genuinely usable free tier. Cost only appears at real scale.

| Layer | Choice | Free tier | Notes |
|---|---|---|---|
| Bot (Phase 0) | Telegram Bot API | Free, unlimited | No approval process |
| Backend | Cloudflare Workers | 100k req/day | Or Fly.io / Render free tier |
| Queue | Cloudflare Queues, or DB-polling worker | Generous | Don't over-engineer |
| Database | Supabase (Postgres) | 500MB + auth included | `pgvector` built in |
| Vector search | `pgvector` in same Postgres | Free | No separate vector DB needed at this scale |
| Video understanding | Gemini Flash | Free tier within rate limits | ⚠️ see privacy note below |
| Transcription (fallback) | Groq Whisper large-v3-turbo | ~2,000 req/day, no card | ~$0.04/hr when paid |
| Embeddings | Gemini embedding API | Free tier | |
| YouTube captions | `youtube-transcript-api` | Free | Zero AI cost when captions exist |
| Instagram fetch | Apify Reel Scraper | ~$5 starting credit | **The only real cost** |
| App framework | React Native (Expo) | Free | One codebase for later iOS |
| Push | Expo Notifications / FCM | Free | |
| Play Store | — | **$25 one-time** | Unavoidable |

> ⚠️ **Privacy caveat on free tiers:** Gemini's free tier permits Google to use submitted content to improve its products. Acceptable while testing with volunteers who are told. **Move to paid before launch**, and state your data handling in the privacy policy — Play requires a live, accurate policy URL.

### Cost per item (once paying)

| Component | Cost |
|---|---|
| Instagram fetch (Apify) | ~$0.0023 |
| Gemini video analysis (60s reel @ 258 tok/sec ≈ 15.5k tokens) | ~$0.004 |
| Embedding | negligible |
| **Total** | **~$0.01 / ₹0.85 per item** |

YouTube with existing captions: near zero — no video processing.

**Free tier must be capped.** A user saving 40 items/day costs ~$12/month. Suggested cap: **15 items/week free.**

### Cost-control levers

1. **Classify before summarizing.** Memes and entertainment get a one-line description, not a full video analysis. If 40% of shares are non-informational, that's 40% off the bill.
2. **YouTube captions first** — skip AI transcription entirely when captions exist.
3. **Dedupe by URL** globally. A viral reel shared by 200 users gets processed once.
4. **Cheap model for classification**, better model only for the summary.

---

## 9. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  CAPTURE                                                │
│  Android share-sheet (ACTION_SEND / text-plain)         │
│  → POST /ingest {url, user_id}                          │
│  → return 200 IMMEDIATELY ("Saved ✓")                   │
└──────────────────────┬──────────────────────────────────┘
                       │  enqueue job
┌──────────────────────▼──────────────────────────────────┐
│  RESOLVE  — SourceAdapter interface                     │
│  ┌───────────┬───────────┬───────────┬───────────┐      │
│  │ YouTube   │ Instagram │  TikTok   │ Generic   │      │
│  │ captions  │ provider  │  (later)  │ link-only │      │
│  │           │ + failover│           │           │      │
│  └───────────┴───────────┴───────────┴───────────┘      │
│  Returns: {caption, transcript?, media_url?, meta}      │
└──────────────────────┬──────────────────────────────────┘
┌──────────────────────▼──────────────────────────────────┐
│  UNDERSTAND                                             │
│  1. Classify → content_type + is_informational          │
│  2. If not informational → 1-line desc, STOP (cheap)    │
│  3. Else → video/transcript into Gemini with the        │
│     template for that content_type                      │
│  4. Output structured JSON, not prose                   │
└──────────────────────┬──────────────────────────────────┘
┌──────────────────────▼──────────────────────────────────┐
│  STORE                                                  │
│  Postgres row + pgvector embedding                      │
│  NO video file. Thumbnail URL + source link only.       │
└──────────────────────┬──────────────────────────────────┘
┌──────────────────────▼──────────────────────────────────┐
│  RETRIEVE                                               │
│  • Semantic search (pgvector cosine + keyword hybrid)   │
│  • Resurfacing ranker → widget + weekly digest          │
└─────────────────────────────────────────────────────────┘
```

### The one architectural rule

**`SourceAdapter` is an interface with swappable implementations.** Every platform-specific fetch lives behind it; everything downstream is platform-agnostic.

This matters because your Instagram provider *will* break. When it does, you swap an adapter — you don't rewrite a pipeline. It's also what makes adding TikTok a one-week job later instead of a refactor.

Implement Instagram with **two providers and automatic failover** from day one.

---

## 10. Data model

```sql
create table users (
  id            uuid primary key,
  created_at    timestamptz default now(),
  tier          text default 'free',
  weekly_quota  int  default 15,
  timezone      text default 'Asia/Kolkata'
);

create table items (
  id              uuid primary key,
  user_id         uuid references users(id),
  url             text not null,
  url_hash        text not null,           -- global dedupe key
  platform        text,                    -- instagram | youtube | other
  status          text,                    -- pending|processing|ready|failed|unsupported

  -- source metadata (attribution is mandatory, see §12)
  creator_handle  text,
  creator_url     text,
  posted_at       timestamptz,
  thumbnail_url   text,
  duration_sec    int,

  -- understanding
  content_type    text,     -- listicle|tutorial|recipe|explainer|news|entertainment
  is_informational boolean,
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

create index on items using ivfflat (embedding vector_cosine_ops);
create index on items (user_id, saved_at desc);
create unique index on items (user_id, url_hash);

-- global processing cache: one viral reel, processed once
create table url_cache (
  url_hash     text primary key,
  payload      jsonb,      -- everything except user-specific fields
  processed_at timestamptz default now()
);
```

**Why `summary` is `jsonb` and not text:** a listicle needs to render as a list, a tutorial as numbered steps, a recipe as ingredients + method. Storing prose forces you to re-parse it forever. Store structure, render per type.

---

## 11. The AI pipeline

### Step 1 — Classify (cheap model, one call)

Returns:
```json
{
  "content_type": "listicle",
  "is_informational": true,
  "topics": ["tax", "personal-finance", "india"],
  "confidence": 0.92
}
```

If `is_informational: false` → store a one-line description and stop. **This is your margin.**

### Step 2 — Templated extraction

One prompt per `content_type`. Never a generic "summarize this."

**`listicle`** →
```json
{
  "headline": "5 tax-saving hacks beyond 80C",
  "items": [
    {"point": "NPS Tier 1 under 80CCD(1B)", "detail": "Extra ₹50k deduction above the 1.5L limit"},
    ...
  ]
}
```

**`tutorial`** → `{ "goal": "...", "steps": [...], "tools_needed": [...] }`
**`explainer`** → `{ "question": "...", "answer": "...", "key_points": [...] }`
**`recipe`** → `{ "ingredients": [...], "method": [...], "time_min": 25 }`

### Prompt rules that matter

- **Extract, don't invent.** If the video doesn't say it, it isn't in the summary. Explicitly instruct: omit rather than fill gaps.
- **Read on-screen text.** Many listicles never speak the items aloud — they display them over music. Audio-only transcription returns nothing useful. This is why video-in beats transcript-in for Instagram.
- **Preserve specifics.** Numbers, brand names, section codes, amounts. Losing "80CCD(1B)" destroys the value.
- **Flag time-sensitivity.** Set `is_time_sensitive` on tax/law/pricing content so the UI can warn that advice may be outdated.

### Step 3 — Embed

Embed `title + summary text + topics` (not the raw transcript — too noisy). Store in `pgvector`.

---

## 12. Search

Hybrid, because pure vector search fails on exact terms:

1. **Vector** — cosine similarity on the query embedding. Handles *"that thing about saving tax"*.
2. **Keyword** — Postgres full-text on title + summary. Handles *"80CCD"*, brand names, handles.
3. **Merge** with reciprocal rank fusion, boost recently-saved on ties.

**Quality bar:** someone types *"the AI tool for presentations"* and finds a reel where the brand name was said once, on screen, in second 14. If search is mediocre, nothing else matters.

---

## 13. Resurfacing engine

The feature that fixes the actual problem. One ranking function, two surfaces (widget + digest).

**Score each item:**

| Signal | Weight | Logic |
|---|---|---|
| Calendar relevance | **highest** | `topics` matched against a date map — tax→Jan-Mar, fitness→Jan, travel→pre-holiday |
| Unread recency | high | saved <7 days, never opened |
| Aging out | medium | saved 60–120 days, never opened |
| Never-opened penalty decay | low | avoid showing the same ignored item forever |
| Already opened | negative | don't resurface consumed items |

**Calendar map is a static config file to start.** Don't build ML for this. A dictionary of `topic → months` gets you 90% of the value in an afternoon.

**Digest:** one push per week, Sunday morning local time. *"4 things you saved this week — 3 min read."*
**Discipline:** one notification per week, maximum. Get muted once and you lose the channel permanently.

---

## 14. Widget

**One card. Not a slideshow.**

```
┌────────────────────────────┐
│ [thumb]  5 tax-saving      │
│          hacks beyond 80C  │
│          NPS Tier 1 gives  │
│          extra ₹50k...     │
│          @financewithsharan│
└────────────────────────────┘
```

Tap → opens directly to that item's full summary.

**Rules:**
- Show a **hook**, never the full summary. The widget's job is to make them tap, not to satisfy the glance.
- ~100 characters of readable content. That's the real budget.
- Item is chosen by the §13 ranker. Never random — irrelevant content on a home screen gets the widget deleted.

**Platform constraint:** Android `AppWidgetProvider` allows a `StackView` and reasonable refresh. iOS WidgetKit does **not** allow animation or timers — you supply a pre-computed timeline of entries and the system renders them, with a limited daily refresh budget. Design for the iOS constraint from the start so the Android version doesn't need rework.

**Expectation setting:** most people never add a widget. This is a retention multiplier for power users, not a growth channel. Don't let it eat weeks.

---

## 15. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Instagram provider breaks** | High / certain | `SourceAdapter` abstraction + two providers with failover. Assume breakage monthly. |
| **Play Store copyright takedown** | High | **Never store video server-side.** Summary + thumbnail + link-back only. Play policy explicitly covers copyrighted content and may require proof of rights. |
| **Meta ToS exposure** | Medium | Logged-off fetching only, via third-party providers. *Meta v. Bright Data* (N.D. Cal., Jan 2024) held Meta's terms don't bar logged-off scraping of public data — but this is US case law, doesn't make scraping per se legal, and **evaporates the moment you use a logged-in session.** No Instagram login, ever. |
| **Bad advice laundering** | Medium | Tax/legal/medical reels are often wrong or outdated. Always display creator handle + original post date + source link. Show a staleness warning on `is_time_sensitive` items. A clean formatted list looks more authoritative than a shaky reel — don't launder credibility. |
| **Nobody returns** | **Existential** | This is exactly what Phase 0 tests. Kill or pivot before the app build. |
| **Habit gap** | High | Their current habit is *one tap* (IG bookmark). You need share → scroll → tap → done, with instant confirmation and zero foreground UI. Any spinner loses. |
| **Crowded category** | Medium | Compete on retrieval + resurfacing, not on summarizing. Vertical focus on knowledge content. |

---

## 16. Success metrics

**Phase 0 gate (the only one that counts):**
- ≥25% of users run a search in week 2 or later

**Phase 1:**
- D7 retention ≥25%
- Median items saved per active user per week ≥3
- **Retrieval rate:** % of saved items opened again after 7+ days — *the north star*
- Search success rate: % of searches ending in an item open

**Anti-metric — watch it and be honest:** if saves are high and retrieval is near zero, you have built a nicer graveyard. That is failure, regardless of how good the DAU chart looks.

---

## 17. Monetization (Phase 3, not before)

**Free:** 15 saves/week, full search, weekly digest, widget.
**Paid (~₹199/mo or ₹1,499/yr):** unlimited saves, export to Notion/Markdown, collections, priority processing, older-archive access.

Rationale: search must be free forever, because search *is* the value demonstration — gating it means users never feel the payoff. Gate volume and export instead.

At ~₹0.85/item cost, a ₹199/mo subscriber is profitable up to ~230 items/month. Watch the top 1% of users; add a soft fair-use ceiling.

---

## 18. Build order

| Week | Deliverable |
|---|---|
| 1 | Telegram bot: YouTube only (captions → classify → template → store). Prove the summary quality. |
| 2 | Add Instagram via Apify. Add `/search`. Ship to 50 users. |
| 3–4 | **Watch. Do not build.** Measure the search metric. Interview 10 users. |
| — | **GATE: search metric passes, or stop.** | 
| 5–8 | Expo Android app: share intent, instant confirm, library, search |
| 9–10 | Weekly digest + resurfacing ranker |
| 11–12 | Widget, polish, Play submission (budget two review cycles) |

**Do not build the app in weeks 1–4.** The most expensive mistake available here is a beautiful app nobody opens twice.

---

## 19. Open decisions

1. **Name.** Needs to signal retrieval, not summarizing.
2. **Onboarding cold-start.** New user has an empty library and search is useless. Options: seed with 5 demo items, or push hard to save 3 things in the first session. Untested.
3. **Instagram provider pair.** Benchmark Apify vs HikerAPI on success rate and latency before committing.
4. **Transcript storage.** Keeping `raw_transcript` improves search but increases DB size and copyright surface area. Lean toward keeping it, private, never displayed in full.
