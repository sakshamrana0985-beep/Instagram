"""Verifies every external service is reachable with the configured keys, and
catches the credential mix-ups that otherwise surface as an opaque error on the
first forwarded link.

Run: python scripts/health_check.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from urllib.parse import quote, urlparse

sys.path.insert(0, ".")

from config import load_settings  # noqa: E402


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_telegram(token: str) -> CheckResult:
    import httpx

    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return CheckResult("Telegram", True, f"bot @{data['result']['username']}")
        return CheckResult("Telegram", False, f"HTTP {resp.status_code}: {data}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Telegram", False, str(exc))


def check_gemini(api_key: str) -> CheckResult:
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        models = list(client.models.list())
        return CheckResult("Gemini", True, f"{len(models)} models visible")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Gemini", False, str(exc))


def check_groq(api_key: str) -> CheckResult:
    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        models = client.models.list()
        return CheckResult("Groq", True, f"{len(models.data)} models visible")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Groq", False, str(exc))


def inspect_service_key(service_key: str) -> str | None:
    """Supabase issues two API keys and only one of them can bypass row-level
    security. Returns a problem description, or None if the key looks right."""
    if service_key.startswith("sb_publishable_") or service_key.startswith("eyJ") and '"anon"' in service_key:
        return (
            "this is the publishable/anon key — copy the secret key instead "
            "(Project Settings > API Keys, the one you have to click to reveal)"
        )
    return None


# Characters a connection URI reads as syntax rather than as part of a password.
_URI_RESERVED = "@/?#"


def inspect_db_url(dsn: str) -> str | None:
    """Catches the ways the Postgres DSN is usually wrong: a placeholder, an API
    key pasted where the database password belongs, or a generated password
    containing characters the URI format reserves."""
    # Checked before parsing: urlparse reads brackets as an IPv6 literal and
    # raises rather than handing back the password.
    if "[" in dsn or "]" in dsn:
        return "still contains [...] — replace the placeholder, brackets included"

    # Parsed by hand rather than with urlparse: an unencoded @ or / in the
    # password is exactly what makes urlparse read the DSN wrongly, so asking it
    # first would hide the problem being looked for.
    _, _, after_scheme = dsn.partition("://")
    userinfo, _, _host = after_scheme.rpartition("@")
    _user, _, password = userinfo.partition(":")

    reserved = sorted({c for c in password if c in _URI_RESERVED})
    if reserved:
        pairs = ", ".join(f"{c} -> {quote(c, safe='')}" for c in reserved)
        return (
            f"the password contains {' '.join(reserved)} , which a connection URI "
            f"reads as syntax. Percent-encode it in SUPABASE_DB_URL ({pairs}) — "
            "the password itself does not change"
        )

    if password.startswith(("sb_publishable_", "sb_secret_", "eyJ")):
        return (
            "the password here is a Supabase API key. This field wants the "
            "database password you set when you created the project — reset it "
            "under Project Settings > Database if you don't have it"
        )
    if not password:
        return "no password in the connection string"
    return None


def check_supabase(url: str, service_key: str) -> CheckResult:
    problem = inspect_service_key(service_key)
    if problem:
        return CheckResult("Supabase", False, problem)

    try:
        from supabase import create_client

        client = create_client(url, service_key)
        client.table("_healthcheck_nonexistent_").select("*").limit(1).execute()
        return CheckResult("Supabase", True, "connected")
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        # A "relation does not exist" error still proves auth + connectivity work.
        if "does not exist" in message or "PGRST" in message:
            return CheckResult("Supabase", True, "connected (no tables yet)")
        return CheckResult("Supabase", False, message)


def check_database(dsn: str) -> CheckResult:
    """The direct asyncpg path the bot actually uses, plus the pgvector
    extension and the migrated schema — Supabase being up says nothing
    about whether migrations/0001_init.sql was ever applied."""
    import asyncio

    problem = inspect_db_url(dsn)
    if problem:
        return CheckResult("Postgres", False, problem)

    async def _check() -> CheckResult:
        import asyncpg

        try:
            conn = await asyncpg.connect(dsn, timeout=10)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            # db.<ref>.supabase.co resolves to IPv6 only. Networks without IPv6
            # fail here with an address-family or unreachable error, and the fix
            # is the pooler host rather than anything about the credentials.
            if urlparse(dsn).hostname and str(urlparse(dsn).hostname).startswith("db."):
                if "Address family" in message or "unreachable" in message or "Connect call failed" in message:
                    return CheckResult(
                        "Postgres",
                        False,
                        "cannot reach the direct connection (it is IPv6-only) — use the "
                        "Session pooler URI from Project Settings > Database instead",
                    )
            return CheckResult("Postgres", False, message)
        try:
            has_vector = await conn.fetchval(
                "select exists (select 1 from pg_extension where extname = 'vector')"
            )
            tables = await conn.fetchval(
                """
                select count(*) from information_schema.tables
                where table_schema = 'public'
                  and table_name in ('users', 'items', 'url_cache', 'search_events', 'item_open_events')
                """
            )
        finally:
            await conn.close()

        if not has_vector:
            return CheckResult("Postgres", False, "pgvector extension missing — run migrations/0001_init.sql")
        if tables < 5:
            return CheckResult(
                "Postgres", False, f"only {tables}/5 tables present — run migrations/0001_init.sql"
            )
        return CheckResult("Postgres", True, "schema applied, pgvector enabled")

    return asyncio.run(_check())


def check_apify(token: str) -> CheckResult:
    try:
        from apify_client import ApifyClient

        client = ApifyClient(token)
        user = client.user().get()
        return CheckResult("Apify", True, f"account {user.get('username', '?')}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Apify", False, str(exc))


def main() -> int:
    settings = load_settings()

    results = [
        check_telegram(settings.telegram_bot_token),
        check_gemini(settings.gemini_api_key),
        check_groq(settings.groq_api_key),
        check_supabase(settings.supabase_url, settings.supabase_service_key),
        check_database(settings.supabase_db_url),
        check_apify(settings.apify_token),
    ]

    print("\nHealth check results:")
    print("-" * 50)
    all_ok = True
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        print(f"[{status}] {r.name:12s} {r.detail}")
        all_ok = all_ok and r.ok
    print("-" * 50)

    if all_ok:
        print("All services reachable.")
        return 0
    print("One or more services failed. Check keys in .env.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
