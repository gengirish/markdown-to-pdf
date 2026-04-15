#!/usr/bin/env python3
"""Minimal IntelliForge Certificates flow: list courses, issue, verify, download PDF.

Requires: pip install httpx
Env: INTELLIFORGE_URL (default https://certs.intelliforge.tech), INTELLIFORGE_API_KEY (if server enforces keys).
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

BASE_URL = os.environ.get("INTELLIFORGE_URL", "https://certs.intelliforge.tech").rstrip("/")
API_KEY = os.environ.get("INTELLIFORGE_API_KEY", "").strip()


def main() -> None:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=60.0) as client:
        # 1. List courses
        courses_resp = client.get("/api/courses")
        courses_resp.raise_for_status()
        courses = courses_resp.json().get("courses") or []
        if not courses:
            print("No courses returned; cannot create certificate.", file=sys.stderr)
            sys.exit(1)
        course_name = courses[0]
        print(f"Using course: {course_name}")

        # 2. Create certificate with idempotency_key
        idem = f"quickstart-{uuid.uuid4()}"
        create_body = {
            "participant_name": "Quickstart Demo User",
            "course_name": course_name,
            "completion_date": "2026-04-15",
            "instructor_name": "IntelliForge AI Team",
            "idempotency_key": idem,
        }
        create_resp = client.post("/api/certificate", json=create_body)
        create_resp.raise_for_status()
        cert = create_resp.json()
        token = cert["token"]
        print(f"Issued certificate_id={cert['certificate_id']} request_id={cert.get('request_id')}")

        # 3. Verify
        verify_resp = client.get(f"/certificate/{token}/verify")
        verify_resp.raise_for_status()
        v = verify_resp.json()
        if not v.get("valid"):
            print("Verification failed:", v, file=sys.stderr)
            sys.exit(1)
        print("Verify OK:", v.get("participant_name"), v.get("course_name"))

        # 4. Download PDF
        pdf_resp = client.get(f"/certificate/{token}/download")
        pdf_resp.raise_for_status()
        out_path = "quickstart_certificate.pdf"
        with open(out_path, "wb") as f:
            f.write(pdf_resp.content)
        print(f"PDF saved to {out_path} ({len(pdf_resp.content)} bytes)")

        # 5. Results
        print("--- Summary ---")
        print("url:", cert.get("url"))
        print("download_url:", cert.get("download_url"))
        print("email_sent:", cert.get("email_sent"))


if __name__ == "__main__":
    main()
