# Getting the bot running on Telegram

Plain-English version. Everything in code is done — this is the part that needs
your accounts and your keys, because they're tied to your identity and card,
not the repo.

Budget: everything below is free. Apify gives ~$5 of starting credit, which is
roughly 2,000 Instagram reels.

---

## Step 1 — Create the bot (2 minutes)

1. Open Telegram, search for **@BotFather**, hit Start.
2. Send `/newbot`.
3. Give it a display name (anything, e.g. "Recall") and then a username that
   must end in `bot` (e.g. `recall_saves_bot`).
4. BotFather replies with a long token like `12345678:AAF...`. **That's your
   `TELEGRAM_BOT_TOKEN`.** Don't paste it anywhere public.

## Step 2 — Create the database (10 minutes)

1. Go to **supabase.com** → sign in → **New project**.
2. Pick any name, set a database password (save it somewhere), pick the region
   closest to you, create. Wait ~2 minutes for it to finish provisioning.
3. Left sidebar → **SQL Editor** → **New query**. Open `migrations/0001_init.sql`
   from this repo, copy the whole file, paste it in, hit **Run**. This creates
   the tables. You should see "Success".
4. Left sidebar → **Project Settings → API Keys**. Supabase gives you two, and
   they are not interchangeable:
   - `sb_publishable_...` — safe to expose, **not** the one we want
   - `sb_secret_...` — the one you have to click to reveal → `SUPABASE_SERVICE_KEY`

   The **Project URL** (Settings → API) → `SUPABASE_URL`.
5. **Project Settings → Database → Connection string**. Two traps here:
   - The password in that string is the **database password from step 2** —
     *not* any of the API keys above. Different thing entirely. Forgot it?
     Reset it on that same page.
   - Delete the square brackets along with the placeholder. `[hunter2]` is
     wrong, `hunter2` is right.
   - Prefer the **Session pooler** URI (`...pooler.supabase.com`) over the
     direct one (`db.<ref>.supabase.co`). The direct host is IPv6-only, so on a
     network without IPv6 it fails with a confusing "network unreachable".

   That string → `SUPABASE_DB_URL`.

## Step 3 — Get the three API keys (10 minutes)

| Key | Where | Notes |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → **Get API key** | Free tier. Does the classifying, summarizing and search embeddings. |
| `GROQ_API_KEY` | console.groq.com → **API Keys** | Free, no card. Only used as a backup when video reading fails. |
| `APIFY_TOKEN` | apify.com → sign up → **Settings → Integrations → API token** | This is the only one that eventually costs money. Free starting credit is plenty for a 50-person test. |

⚠️ Google's free Gemini tier lets Google use what you send to improve their
products. Fine for volunteer testing as long as you tell testers. Move to the
paid tier before any real launch (PRD §8).

## Step 4 — Put the keys in a file

In the project folder:

```bash
cp .env.example .env
```

Open `.env` in any text editor and paste each value after the `=`. No quotes,
no spaces around the `=`. `.env` is gitignored — it never leaves your machine.

## Step 5 — Check everything works

```bash
pip install -e ".[dev]"
python scripts/health_check.py
```

You want six `[OK ]` lines: Telegram, Gemini, Groq, Supabase, Postgres, Apify.

Common failures:
- **Postgres FAIL "run migrations"** — step 2.3 didn't run. Redo it.
- **Postgres FAIL "the password here is a Supabase API key"** — you pasted a
  `sb_...` key where the database password goes. See step 2.5.
- **Postgres FAIL "IPv6-only"** — switch to the Session pooler URI.
- **Supabase FAIL "this is the publishable/anon key"** — grab the secret one.
- **Telegram FAIL** — token copied with a missing character.
- **Apify FAIL** — token from the wrong account or not yet activated.

## Step 6 — Run the bot

```bash
python -m bot.main
```

Leave that terminal open — the bot only runs while it's running. Now, in
Telegram, open your bot and:

1. Send `/start` → it explains itself.
2. Paste a **YouTube link that has captions** (any normal talking-head video).
   You should get "Saved ✓" instantly, then it edits into a real summary
   within ~10 seconds. YouTube first because it costs nothing.
3. Paste an **Instagram reel link** — one with information in it, ideally with
   text on screen. Same flow, ~30–60 seconds (it downloads the video and reads
   it).
4. Send `/search tax` (or whatever the reel was about) → your item comes back
   with an **Open** button.
5. Send `/stats` → your counts and saves remaining this week.
6. Send `/admin` → the Phase 0 gate metrics across all users.

If something breaks, the terminal running the bot prints exactly which step
failed (`stage=resolve`, `stage=classify`, `llm_call ... status=failed`).

## Step 7 — What to actually watch during the test

Per PRD §6 the only metric that decides anything is: **does anyone run
`/search` in week 2 or later?** `/admin` shows it directly, including whether
you're above the 25% gate. Saves being high with searches near zero is the
failure case, not a good chart.

---

## Notes and limits, honestly

- **Instagram reels cost money** (~$0.0023 each via Apify) and **YouTube with
  captions is free**. Test with YouTube while you're checking that things work.
- **The free cap is 15 saves per user per week**, rolling. Raise it for
  yourself with SQL in Supabase:
  `update users set weekly_quota = 500 where telegram_id = <your telegram id>;`
- **The second Instagram provider is a stub.** If Apify breaks, Instagram
  breaks — the failover path exists but `HikerAPIProvider` raises
  `NotImplementedError` (PRD §19 leaves the provider choice open pending a
  benchmark). Nothing else in the code needs to change when you implement it.
- **`/admin` is open to everyone.** Fine for 50 volunteers you know, gate it
  before any wider link.
- **The bot runs on your machine.** Close the terminal and it stops answering.
  For a real 50-person test, run it on a small always-on box (Fly.io / Render
  free tier).
