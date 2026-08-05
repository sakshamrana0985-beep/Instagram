# Recall (Phase 0)

Telegram bot that turns saved Instagram/YouTube videos into searchable notes.
See `docs/PRD-and-Architecture.md` for the full spec and
`docs/claude-code-build-plan.md` for the build sequence this repo follows.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # fill in your keys
python scripts/health_check.py
```

## Layout

- `adapters/` — one file per platform (`SourceAdapter` interface), see CLAUDE.md rule 1
- `pipeline/` — classify → summarize → embed → store
- `storage/` — Supabase/Postgres access layer
- `bot/` — Telegram bot handlers
- `tests/` — pytest suite
