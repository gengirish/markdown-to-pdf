#!/usr/bin/env python3
"""Batch-verify certificate tokens for audits (stdin or file, one token per line).

Requires: pip install httpx
Comments (#) and blank lines are ignored. Batches of up to 100 tokens per API call.

Env: INTELLIFORGE_URL (optional; public verify endpoint works without API key).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import httpx

BASE_URL = os.environ.get("INTELLIFORGE_URL", "https://certs.intelliforge.tech").rstrip("/")


def read_tokens(path: str | None) -> list[str]:
    fh = open(path, encoding="utf-8") if path else sys.stdin
    try:
        out: list[str] = []
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
        return out
    finally:
        if path:
            fh.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Batch verify certificate tokens.")
    p.add_argument("tokens_file", nargs="?", help="File with one token per line (default: stdin)")
    args = p.parse_args()
    tokens = read_tokens(args.tokens_file)
    if not tokens:
        print("No tokens to verify.", file=sys.stderr)
        sys.exit(1)

    counts: Counter[str] = Counter()
    details: list[dict] = []

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        for i in range(0, len(tokens), 100):
            chunk = tokens[i : i + 100]
            r = client.post("/api/certificates/verify", json={"tokens": chunk})
            r.raise_for_status()
            body = r.json()
            for row in body.get("results", []):
                details.append(row)
                if row.get("valid"):
                    counts["valid"] += 1
                elif row.get("revoked"):
                    counts["revoked"] += 1
                else:
                    counts["invalid"] += 1

    print("--- Compliance report ---")
    print(f"Total tokens: {len(tokens)}")
    print(f"Valid:        {counts['valid']}")
    print(f"Invalid:      {counts['invalid']}")
    print(f"Revoked:      {counts['revoked']}")
    bad = [d for d in details if not d.get("valid")]
    if bad:
        print(f"\nFirst issues (up to 5): {bad[:5]}")


if __name__ == "__main__":
    main()
