"""Verifies all five external services are reachable with the configured keys.

Run: python scripts/health_check.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

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


def check_supabase(url: str, service_key: str) -> CheckResult:
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
