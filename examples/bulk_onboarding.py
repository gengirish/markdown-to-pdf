#!/usr/bin/env python3
"""Enterprise-style bulk certificate issuance from a CSV (admin API).

CSV columns: name,email,course (header row required). Optional: completion_date (YYYY-MM-DD).

Requires: pip install httpx
Env: INTELLIFORGE_URL, INTELLIFORGE_ADMIN_KEY

Note: POST /api/admin/certificates/bulk requires the server to have DATABASE_URL configured.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date

import httpx

BASE_URL = os.environ.get("INTELLIFORGE_URL", "https://certs.intelliforge.tech").rstrip("/")
ADMIN_KEY = os.environ.get("INTELLIFORGE_ADMIN_KEY", "").strip()


def main() -> None:
    if not ADMIN_KEY:
        print("Set INTELLIFORGE_ADMIN_KEY.", file=sys.stderr)
        sys.exit(1)

    p = argparse.ArgumentParser(description="Bulk issue certificates from CSV.")
    p.add_argument("input_csv", help="Input CSV with name,email,course")
    p.add_argument("-o", "--output", default="bulk_results.csv", help="Output CSV path")
    args = p.parse_args()
    today = date.today().isoformat()

    entries: list[dict] = []
    with open(args.input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            course = (row.get("course") or "").strip()
            completion = (row.get("completion_date") or today).strip()
            if not name or not course:
                continue
            entries.append(
                {
                    "participant_name": name,
                    "participant_email": email,
                    "course_name": course,
                    "completion_date": completion,
                    "instructor_name": "IntelliForge AI Team",
                }
            )

    if not entries:
        print("No valid rows.", file=sys.stderr)
        sys.exit(1)

    headers = {"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=120.0) as client:
        resp = client.post("/api/admin/certificates/bulk", json={"entries": entries})
        resp.raise_for_status()
        body = resp.json()

    total, ok, fail = body["total"], body["succeeded"], body["failed"]
    print(f"Bulk complete: total={total} succeeded={ok} failed={fail}")

    fieldnames = ["index", "status", "participant_name", "course_name", "url", "download_url", "error"]
    with open(args.output, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in body.get("results", []):
            row = {k: r.get(k, "") for k in fieldnames}
            w.writerow(row)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
