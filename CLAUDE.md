# Recall — Phase 0

Telegram bot. User forwards a social video link → gets a structured summary →
can search their history later. Full spec in `docs/PRD-and-Architecture.md`
and `docs/claude-code-build-plan.md`.

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
