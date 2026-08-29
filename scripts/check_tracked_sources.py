#!/usr/bin/env python3
"""Fail if .gitignore is hiding source files.

Written after the stock Python .gitignore block's unanchored `lib/` rule
silently swallowed apps/web/lib/ — the CertForge API client — so the files
were invisible to `git add` and would have been lost. Source disappearing
is a far worse failure than a stray build artifact appearing, and nothing
in CI would have noticed.

Lists everything git ignores under the source trees, drops the paths that
are genuinely build output, and fails on whatever is left.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

# Trees that hold hand-written code. Anything ignored in here is suspect.
SOURCE_ROOTS = ("apps/", "sdk/", "scripts/", "examples/", "e2e/")

SOURCE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".css", ".scss", ".html", ".toml", ".yml", ".yaml",
}

# Binary assets are only source when they sit in a test or fixture tree —
# a stray screenshot elsewhere under apps/ is not worth failing CI over.
# Added after `*.pdf` was blanket-ignored, which would have silently hidden
# any PDF fixture committed under apps/api/tests/.
FIXTURE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                    ".ttf", ".otf", ".woff", ".woff2", ".docx", ".csv"}

FIXTURE_DIRS = {"tests", "test", "fixtures", "__fixtures__", "testdata"}

# Directories that are build output or vendored dependencies. A file ignored
# because it sits in one of these is ignored correctly.
ARTIFACT_DIRS = {
    "node_modules", "dist", "build", ".next", ".turbo", ".vercel",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "venv", ".venv", "env", ".env", "coverage", "htmlcov",
    "playwright-report", "test-results", "blob-report", ".swc",
}


def ignored_files() -> list[str]:
    """Paths git is ignoring, excluding those already tracked."""
    out = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def is_suspect(path: str) -> bool:
    if not path.startswith(SOURCE_ROOTS):
        return False
    parts = PurePosixPath(path).parts
    if any(part in ARTIFACT_DIRS for part in parts):
        return False
    # Generated type stubs and lockfiles are not hand-written source.
    if path.endswith((".d.ts", ".lock", ".log")):
        return False
    suffix = PurePosixPath(path).suffix
    if suffix in FIXTURE_SUFFIXES:
        return any(part in FIXTURE_DIRS for part in parts)
    return suffix in SOURCE_SUFFIXES


def main() -> int:
    suspects = sorted(p for p in ignored_files() if is_suspect(p))
    if not suspects:
        print("OK: no source files are hidden by .gitignore")
        return 0

    print("ERROR: .gitignore is hiding files that look like source:\n", file=sys.stderr)
    for path in suspects:
        rule = subprocess.run(
            ["git", "check-ignore", "-v", path],
            capture_output=True, text=True,
        ).stdout.strip()
        print(f"  {path}\n      matched by: {rule}", file=sys.stderr)
    print(
        "\nEither anchor the offending pattern (e.g. `lib/` -> `/lib/`) or add the"
        "\npath to ARTIFACT_DIRS in this script if it really is build output.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
