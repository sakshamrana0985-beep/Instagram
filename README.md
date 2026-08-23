# Recall (Phase 0)

Telegram bot that turns saved Instagram/YouTube videos into searchable notes.
See `docs/PRD-and-Architecture.md` for the full spec and
`docs/claude-code-build-plan.md` for the build sequence this repo follows.

## Setup

```bash
bash setup.sh    # Mac/Linux - installs, asks for your keys, starts the bot
.\setup.ps1      # Windows PowerShell, same thing
```

Doing it by hand instead:

```bash
pip install -e ".[dev]"
cp .env.example .env   # fill in your keys
python scripts/health_check.py
python -m bot.main
```

**`docs/SETUP.md` walks through every account and key step by step** — BotFather,
Supabase, the three API keys, and what to send the bot to check it works.

## Running the tests

The suite is 64 tests. Half of them are pure logic (adapters, classify,
summarize, render) and need nothing; the other half talk to Postgres+pgvector.
No real API keys or Supabase project are needed either way — every external
provider is stubbed.

```bash
pip install -e ".[dev]"
./scripts/setup_test_db.sh      # Postgres+pgvector, docker or local server
python -m pytest
```

`setup_test_db.sh` picks docker (`pgvector/pgvector:pg16`) when a daemon is
running and the locally-installed PostgreSQL otherwise; force either with
`RECALL_TEST_DB_MODE=docker|native`. It only creates the role and an empty
database — the schema in `migrations/` is applied by the test session itself,
so a blank database is enough. `docker-compose.test.yml` does the same job if
you prefer compose.

Without a database the DB-backed tests skip and the rest still pass. To make
that a failure instead (CI does this), set `RECALL_REQUIRE_DB=1`. Point the
suite at a different database with `TEST_DATABASE_URL`.

```bash
python -m pytest tests/test_search.py -v     # one file
python -m pytest -q -rs                      # show why anything skipped
```

### What needs real keys

Only the things that call live providers, none of which are part of `pytest`:

- `python scripts/health_check.py` — pings all five services with your `.env`
- `python scripts/classify_accuracy.py`, `scripts/summarize_eval.py` — Gemini
- `python -m bot.main` — running the bot for real

## Layout

- `adapters/` — one file per platform (`SourceAdapter` interface), see CLAUDE.md rule 1
- `pipeline/` — classify → summarize → embed → store
- `storage/` — Supabase/Postgres access layer
- `bot/` — Telegram bot handlers
- `tests/` — pytest suite
- `.github/workflows/tests.yml` — CI: full suite against pgvector on every push
