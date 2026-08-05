# Claude Code Build Plan — Phase 0

**Goal:** a working Telegram bot in ~10 focused sessions, ending with the week-4 gate.
**Not in this plan:** the Android app. Don't build it until the gate passes.

---

## Before you open Claude Code

Get these first. Claude Code can't do them for you, and being blocked mid-session wastes context.

| Item | Where | Cost |
|---|---|---|
| Telegram bot token | message `@BotFather` on Telegram | free |
| Gemini API key | aistudio.google.com | free tier |
| Groq API key | console.groq.com | free, no card |
| Supabase project | supabase.com — new project, copy URL + service key | free |
| Apify token | apify.com — has starting credit | ~$5 credit |

Put them in `.env` immediately. Add `.env` to `.gitignore` **before** the first commit.

Then:

```bash
mkdir recall && cd recall
git init
# drop PRD-and-Architecture.md into ./docs/
claude
```

---

## The CLAUDE.md to create first

Session 1 is just this file. It's the single highest-leverage thing in the whole build — Claude Code reads it every session, so anything in here you don't have to repeat.

Create `CLAUDE.md` at repo root:

````markdown
# Recall — Phase 0

Telegram bot. User forwards a social video link → gets a structured summary →
can search their history later. Full spec in `docs/PRD-and-Architecture.md`.

## Stack
- Python 3.11, `python-telegram-bot` (async)
- Supabase Postgres + pgvector
- Gemini Flash (classify, summarize, embed), Groq Whisper (audio fallback)
- Apify (Instagram), youtube-transcript-api (YouTube)

## Architecture rules — do not violate

1. **SourceAdapter is an interface.** Every platform fetch implements
   `async def fetch(url) -> SourceResult`. Instagram/YouTube/Generic are separate
   files. Nothing downstream of the adapter may contain platform-specific logic.
   Adding a platform = adding one file. If a change needs edits outside
   `adapters/`, the abstraction is wrong — stop and flag it.

2. **Never store video files.** Metadata, transcript, summary, thumbnail URL,
   source link only. This is a legal constraint, not a preference.

3. **Never authenticate to Instagram.** No login, no session, no cookies.
   Third-party providers only, logged-off. Non-negotiable.

4. **Classify before summarizing.** Non-informational content (memes,
   entertainment) gets a one-line description and stops. This is the cost model.

5. **Summaries are structured JSON, never prose.** Shape depends on
   `content_type`. Store as jsonb.

6. **Dedupe globally by url_hash** via `url_cache` before any paid API call.

## Code conventions
- Type hints everywhere. `pydantic` models for all LLM output.
- Every external API call: retry with backoff, and a typed failure result.
  Never let a provider failure crash the handler.
- No secrets in code. `os.environ` only.
- Log every LLM call: model, token count, latency, cost estimate.

## Working style
- Small commits, one concern each.
- Write the test before the implementation for anything with logic.
- Ask before adding a dependency.
- If a session's task is ambiguous, ask rather than guess.
````

---

## Session sequence

Each session = one Claude Code conversation. Start fresh between them (`/clear`) so context stays clean.

---

### Session 1 — Scaffold

```
Read docs/PRD-and-Architecture.md, sections 9 and 10.

Set up the project skeleton only — no logic yet:
- pyproject.toml with the stack from CLAUDE.md
- Directory structure: adapters/, pipeline/, storage/, bot/, tests/
- config.py loading env vars with validation that fails loudly on missing keys
- .env.example, .gitignore
- A health-check script that verifies all five API keys work

Then run the health check and show me the output.
```

**Verify:** health check passes for all five services. Fix keys now, not later.

---

### Session 2 — Database

```
Implement the schema from PRD section 10 as a Supabase migration.

Add storage/db.py with typed functions:
- upsert_item, get_item, list_items(user_id), update_item_status
- check_url_cache(url_hash), write_url_cache
- vector_search(user_id, embedding, limit)

Use pydantic models matching the table shapes.
Write tests against a local Postgres with pgvector.
```

**Verify:** tests pass. Open Supabase dashboard, confirm the tables exist.

---

### Session 3 — SourceAdapter + YouTube

```
Define the SourceAdapter interface per CLAUDE.md rule 1:

  SourceResult = {platform, caption, transcript, media_url, creator_handle,
                  creator_url, posted_at, thumbnail_url, duration_sec}

Implement two adapters:
- YouTubeAdapter — youtube-transcript-api, no AI cost when captions exist
- GenericAdapter — link-only fallback, status='unsupported'

Add a registry that picks an adapter by URL pattern.
Test with 5 real YouTube URLs including one with no captions.
```

**Verify:** the no-captions case returns a clean typed failure, not an exception.

---

### Session 4 — The classifier

```
Implement pipeline/classify.py per PRD section 11 step 1.

Gemini Flash-Lite, returns pydantic model:
  {content_type, is_informational, topics[], confidence}

content_type ∈ listicle|tutorial|recipe|explainer|news|entertainment

Build a test set of 20 real examples (I'll paste transcripts) with my hand-
labels, and a script that reports accuracy per class.
```

**Verify:** accuracy above ~85%. Iterate the prompt in this session until it is — this gate protects your whole cost model.

---

### Session 5 — Summary templates

**The most important session. Slow down here.**

```
Implement pipeline/summarize.py per PRD section 11 step 2.

One prompt template per content_type, each returning a distinct pydantic
schema. Prompt rules from the PRD, enforce all four:
- extract only, never invent — omit rather than fill gaps
- read on-screen text, not just audio
- preserve exact numbers, brand names, section codes, amounts
- set is_time_sensitive on tax/legal/pricing/medical content

Run against my 20-item test set. Print each summary next to the transcript
so I can eyeball whether anything was invented or lost.
```

**Verify manually, item by item.** Hallucination here poisons the product — a confident wrong tax summary is worse than no app. Do not proceed until the output is clean.

---

### Session 6 — Instagram adapter

```
Implement InstagramAdapter behind the same interface.

Requirements:
- Provider abstraction underneath: Apify as primary, a second provider stub
  with automatic failover on failure or timeout
- Logged-off third-party fetch only, no auth (CLAUDE.md rule 3)
- Where transcript is unavailable, pass media to Gemini for video understanding
  rather than audio-only transcription (on-screen-text case)
- Check url_cache before any paid call

Test with 5 real reel URLs: one voiceover, one text-on-screen-only, one meme.
```

**Verify:** the text-on-screen reel produces a real summary. That's the case that separates you from lazy competitors.

---

### Session 7 — Pipeline wiring

```
Wire the full path in pipeline/process.py:

  url → cache check → adapter → classify → (stop if not informational)
      → summarize → embed → store

Job runs async; the caller returns immediately.
Every stage failure updates item.status and is logged with cost.
Add a CLI: `python -m recall.process <url> --user <id>` for testing.
```

**Verify:** run 10 mixed URLs. Check the cost log — confirm non-informational items skipped the expensive path.

---

### Session 8 — The bot

```
Implement the Telegram bot:
- Any forwarded/pasted link → reply "Saved ✓" IMMEDIATELY, process in
  background, then edit the message with the summary when ready
- Render summaries by content_type: listicle as a list, tutorial as numbered
  steps, etc. Always show creator handle + original post date + source link.
- Staleness warning on is_time_sensitive items
- /search <query> — hybrid search, results as tappable cards
- /stats — items saved, items opened

Instant acknowledgement is a hard requirement. No spinner, no waiting.
```

**Verify:** forward a reel while distracted. If the "Saved ✓" isn't instant, fix it before shipping.

---

### Session 9 — Hybrid search

```
Implement search per PRD section 12:
- vector (pgvector cosine) + keyword (Postgres full-text)
- merge with reciprocal rank fusion, recency boost on ties

Test the two queries that matter:
- "that thing about saving tax" → finds the tax reel (semantic)
- "80CCD" → finds it by exact term (keyword)

Both must work. Show me the ranked results for 10 test queries.
```

**Verify:** both query styles succeed. Vector-only will fail the second one — that's why it's hybrid.

---

### Session 10 — Instrumentation

```
Add analytics, because the week-4 gate depends on it:
- log every search: user, query, whether it ended in an item open
- log every item open with days_since_saved
- /admin command showing: total users, items saved, searches run,
  % of users who searched in week 2+, retrieval rate

This last number is the gate. Make it impossible to misread.
```

**Verify:** you can answer *"did anyone search in week 2?"* in one command.

---

## Then stop building

Ship to 50 people. Weeks 3–4 you watch and interview. **Resist adding features.** The gate is:

> ≥25% of users run a search in week 2 or later.

Pass → start the Android app. Fail → the retrieval premise is wrong; pivot cheap.

---

## Guardrails for working with Claude Code

**Do:**
- One session per task. `/clear` between them — stale context degrades output.
- Make it run the tests and show real output, not claims of success.
- Review anything touching prompts yourself. Session 5 especially.
- Commit at the end of every session.

**Don't:**
- Let it build ahead. If it starts scaffolding the Android app in session 3, stop it.
- Accept "it works" without seeing output.
- Let it add dependencies silently — CLAUDE.md forbids this; enforce it.
- Skip session 4's accuracy gate. Everything cost-related rests on classification.

**When something breaks:** paste the full error and let it read the file itself. Don't paraphrase stack traces.

---

## Realistic time

Sessions 1–3 are fast — a day if you're focused. Sessions 4 and 5 are the slow ones; budget several days of prompt iteration each, because that's where product quality actually lives. Sessions 6–10, another few days.

**Two weeks to a shipped bot is realistic. One week is not.**
