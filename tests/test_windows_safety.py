"""Windows PowerShell 5.1 reads .ps1 files as ANSI, not UTF-8. A single em dash
becomes three mojibake bytes and the script dies with a parser error before it
runs a line. The same applies to anything the wizard prints to a console whose
code page cannot encode it.

Cheap to assert, so assert it rather than rediscover it on someone's machine.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CONSOLE_FACING = [
    ROOT / "setup.ps1",
    ROOT / "setup.sh",
    ROOT / "scripts" / "first_run.py",
    ROOT / "scripts" / "health_check.py",
]


@pytest.mark.parametrize("path", CONSOLE_FACING, ids=lambda p: p.name)
def test_console_facing_files_are_pure_ascii(path):
    offenders = [
        (line_no, char)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for char in line
        if ord(char) > 127
    ]

    assert not offenders, f"non-ASCII in {path.name}: {offenders[:5]}"


def test_powershell_script_does_not_use_stop_preference():
    """Under Stop, ordinary stderr from pip or the py launcher becomes fatal.
    Only real assignments count - the script explains the choice in a comment."""
    code_lines = [
        line
        for line in (ROOT / "setup.ps1").read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]

    assert not [line for line in code_lines if 'ErrorActionPreference = "Stop"' in line]
