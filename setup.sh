#!/usr/bin/env bash
# One command to get from a fresh clone to a running bot, on Mac or Linux:
#
#     bash setup.sh
#
# Creates an isolated Python environment, installs what the bot needs, then
# hands over to the setup wizard. Safe to re-run — it reuses what exists.
set -euo pipefail
cd "$(dirname "$0")"

need_version="3.11"
python_bin=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"; then
      python_bin="$candidate"
      break
    fi
  fi
done

if [ -z "$python_bin" ]; then
  echo "Python $need_version or newer is not installed."
  echo "Install it from https://www.python.org/downloads/ then run this again."
  exit 1
fi

echo "Using $($python_bin --version)"

if [ ! -d .venv ]; then
  echo "Creating an isolated environment (.venv)..."
  "$python_bin" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "Installing dependencies (a minute or two the first time)..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev]"

echo
python scripts/first_run.py "$@"
