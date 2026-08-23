"""Interactive first-run setup: asks for each key in plain language, checks it
immediately, writes .env, and starts the bot.

Written for someone who does not read Python. Every prompt says where to get
the value and what it looks like; every failure says what to do about it,
never a stack trace.

    python scripts/first_run.py            # ask for anything missing
    python scripts/first_run.py --check    # only verify what is already in .env
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.health_check import (  # noqa: E402
    CheckResult,
    check_apify,
    check_database,
    check_gemini,
    check_groq,
    check_supabase,
    check_telegram,
    inspect_db_url,
    inspect_service_key,
)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

def _colours_supported() -> bool:
    """The classic Windows PowerShell console renders escape codes literally,
    turning every line into visible garbage. Windows Terminal and VS Code both
    announce themselves; anything else on Windows gets plain text."""
    if os.name != "nt":
        return sys.stdout.isatty()
    return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))


if _colours_supported():
    GREEN, RED, YELLOW = "\033[32m", "\033[31m", "\033[33m"
    DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
else:
    GREEN = RED = YELLOW = DIM = BOLD = RESET = ""

# A Windows console defaults to a legacy code page that cannot encode every
# character; replace rather than crash the wizard on an unlucky error message.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


@dataclass
class Step:
    var: str
    title: str
    where: str
    looks_like: str


STEPS = [
    Step(
        "TELEGRAM_BOT_TOKEN",
        "Telegram bot token",
        "Open Telegram, message @BotFather, send /newbot, follow the two questions.",
        "12345678:AAF...",
    ),
    Step(
        "GEMINI_API_KEY",
        "Google Gemini key (reads the videos)",
        "aistudio.google.com -> 'Get API key'. Free.",
        "a long string of letters and numbers",
    ),
    Step(
        "GROQ_API_KEY",
        "Groq key (backup transcription)",
        "console.groq.com -> API Keys. Free, no card needed.",
        "gsk_...",
    ),
    Step(
        "SUPABASE_URL",
        "Supabase project URL (your database)",
        "supabase.com -> your project -> Project Settings -> API -> Project URL.",
        "https://something.supabase.co",
    ),
    Step(
        "SUPABASE_SERVICE_KEY",
        "Supabase SECRET key",
        "Same page -> API Keys. Use the SECRET one you have to click to reveal, "
        "not the publishable one.",
        "sb_secret_...",
    ),
    Step(
        "SUPABASE_DB_URL",
        "Supabase database connection string",
        "Project Settings -> Database -> Connection string -> Session pooler. "
        "Replace the [YOUR-PASSWORD] placeholder (brackets too) with your database password.",
        "postgresql://postgres.abc:PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres",
    ),
    Step(
        "APIFY_TOKEN",
        "Apify token (fetches Instagram reels)",
        "apify.com -> Settings -> Integrations -> API token. Free starting credit.",
        "apify_api_...",
    ),
]

CHECKERS = {
    "TELEGRAM_BOT_TOKEN": lambda env: check_telegram(env["TELEGRAM_BOT_TOKEN"]),
    "GEMINI_API_KEY": lambda env: check_gemini(env["GEMINI_API_KEY"]),
    "GROQ_API_KEY": lambda env: check_groq(env["GROQ_API_KEY"]),
    "SUPABASE_SERVICE_KEY": lambda env: check_supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"]),
    "SUPABASE_DB_URL": lambda env: check_database(env["SUPABASE_DB_URL"]),
    "APIFY_TOKEN": lambda env: check_apify(env["APIFY_TOKEN"]),
}


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Parses a .env without needing python-dotenv installed yet."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    lines = ["# Written by scripts/first_run.py. Keep this file private.", ""]
    for step in STEPS:
        lines.append(f"{step.var}={values.get(step.var, '')}")
    path.write_text("\n".join(lines) + "\n")


def mask(value: str) -> str:
    """Never echo a whole secret back to a terminal someone may screen-share."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def encode_db_password(dsn: str) -> str:
    """Percent-encodes reserved characters in the password so a generated
    password containing @ / ? does not break the connection string."""
    scheme, sep, rest = dsn.partition("://")
    if not sep:
        return dsn
    userinfo, at, host = rest.rpartition("@")
    if not at:
        return dsn
    user, colon, password = userinfo.partition(":")
    if not colon:
        return dsn
    return f"{scheme}://{user}:{quote(password, safe='%')}@{host}"


def normalize(var: str, value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if var == "SUPABASE_DB_URL":
        value = value.replace("[", "").replace("]", "")
        value = encode_db_password(value)
    return value


# Most of these values announce what they are. Pasting into the wrong question
# is the single most common mistake, and it costs a full round trip to discover
# from a 404, so name the mix-up at the prompt instead.
_FINGERPRINTS: list[tuple[str, re.Pattern[str], str]] = [
    ("SUPABASE_DB_URL", re.compile(r"^postgres(ql)?://"), "database connection string"),
    ("SUPABASE_URL", re.compile(r"^https://[a-z0-9-]+\.supabase\.co/?$"), "Supabase project URL"),
    ("SUPABASE_SERVICE_KEY", re.compile(r"^sb_(secret|publishable)_"), "Supabase API key"),
    ("GROQ_API_KEY", re.compile(r"^gsk_"), "Groq key"),
    ("APIFY_TOKEN", re.compile(r"^apify_"), "Apify token"),
    ("TELEGRAM_BOT_TOKEN", re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$"), "Telegram bot token"),
]

# What each field must look like, where that is knowable. Gemini keys have no
# stable shape, so they are only checked against the fingerprints above.
_EXPECTED = {
    "TELEGRAM_BOT_TOKEN": (re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$"), "digits, a colon, then a long code"),
    "GROQ_API_KEY": (re.compile(r"^gsk_"), "it should start with gsk_"),
    "APIFY_TOKEN": (re.compile(r"^apify_"), "it should start with apify_"),
}


def identify(value: str) -> tuple[str, str] | None:
    """Which field a pasted value belongs to, if it is recognisable."""
    for var, pattern, label in _FINGERPRINTS:
        if pattern.match(value):
            return var, label
    return None


def prevalidate(var: str, value: str) -> str | None:
    """Cheap format checks that run before any network call."""
    if not value:
        return "empty"

    identified = identify(value)
    if identified is not None and identified[0] != var:
        return f"that looks like your {identified[1]}, not this one - check you are on the right question"

    expected = _EXPECTED.get(var)
    if expected is not None and not expected[0].match(value):
        return f"that does not look right - {expected[1]}"
    if var == "SUPABASE_SERVICE_KEY":
        return inspect_service_key(value)
    if var == "SUPABASE_DB_URL":
        if not value.startswith("postgres"):
            return "that does not look like a connection string - it should start with postgresql://"
        return inspect_db_url(value)
    if var == "SUPABASE_URL" and not urlparse(value).scheme.startswith("http"):
        return "that should start with https://"
    return None


def _report(result: CheckResult) -> bool:
    colour, label = (GREEN, "works") if result.ok else (RED, "problem")
    print(f"  {colour}{label}{RESET}: {result.detail}")
    return result.ok


def run_checks(values: dict[str, str]) -> bool:
    print(f"\n{BOLD}Checking each service...{RESET}")
    all_ok = True
    for var, checker in CHECKERS.items():
        print(f"\n{BOLD}{var}{RESET}")
        try:
            ok = _report(checker(values))
        except Exception as exc:  # noqa: BLE001 - a checker must never end the wizard
            print(f"  {RED}problem{RESET}: {exc}")
            ok = False
        all_ok = all_ok and ok
    return all_ok


def ask_for(step: Step, existing: str) -> str:
    print(f"\n{BOLD}{step.title}{RESET}")
    print(f"  {DIM}{step.where}{RESET}")
    print(f"  {DIM}Looks like: {step.looks_like}{RESET}")
    while True:
        if existing:
            raw = input(f"  Currently {mask(existing)}. Enter to keep, or paste a new one: ").strip()
            if not raw:
                return existing
        else:
            raw = input("  Paste it here: ")

        answer = normalize(step.var, raw)
        problem = prevalidate(step.var, answer)
        if problem is None:
            return answer

        # A replacement is checked as strictly as a first answer: overwriting a
        # good value with a misplaced paste is the failure this exists to stop.
        print(f"  {YELLOW}{problem}{RESET}")
        print(f"  {DIM}Try again, or press Ctrl+C to stop.{RESET}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the existing .env, ask nothing")
    args = parser.parse_args()

    values = read_env()

    if not args.check:
        print(f"{BOLD}Recall setup{RESET}")
        print("Seven values to collect. Each one says where to find it.")
        print(f"{DIM}Nothing leaves your computer - they go into a private .env file.{RESET}")
        for step in STEPS:
            values[step.var] = ask_for(step, values.get(step.var, ""))
        write_env(values)
        print(f"\n{GREEN}Saved to .env{RESET}")

    missing = [s.var for s in STEPS if not values.get(s.var)]
    if missing:
        print(f"\n{RED}Still missing: {', '.join(missing)}{RESET}")
        print("Run this again without --check to fill them in.")
        return 1

    if not run_checks(values):
        print(f"\n{RED}Some services did not answer.{RESET} Fix the ones marked 'problem' above,")
        print("then run:  python scripts/first_run.py --check")
        return 1

    print(f"\n{GREEN}Everything works.{RESET}")
    print("\nOne last thing: open your Supabase SQL editor and run the contents of")
    print("migrations/0001_init.sql if you have not already - that creates the tables.")
    if input("\nStart the bot now? [Y/n] ").strip().lower() in ("", "y", "yes"):
        print(f"\n{DIM}Starting. Leave this window open; Ctrl+C stops the bot.{RESET}\n")
        return subprocess.call([sys.executable, "-m", "bot.main"])
    print("\nWhen you are ready:  python -m bot.main")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped. Nothing was lost - run the same command again to continue.")
        sys.exit(1)
