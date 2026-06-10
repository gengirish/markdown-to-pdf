"""
Mint a sample VTU-style internship completion certificate (Forge letterhead + verify link).

Requires the API running (e.g. uvicorn api.index:app --port 8000) and the course name
registered on the server (fallback list includes "VTU Industry Internship – IntelliForge AI Programme").

Usage:
  python examples/issue_aayush_internship_certificate.py
  python examples/issue_aayush_internship_certificate.py --url http://localhost:8000 --out ./Aayush_Internship.pdf
"""

from __future__ import annotations

import argparse
import sys

import requests


def main() -> None:
    p = argparse.ArgumentParser(description="Issue sample internship certificate and save PDF.")
    p.add_argument("--url", default="http://localhost:8000", help="Certificate API base URL")
    p.add_argument(
        "--out",
        default="Aayush_Kulkarni_Internship_Certificate.pdf",
        help="Output path for downloaded PDF",
    )
    args = p.parse_args()
    base = args.url.rstrip("/")

    course = "VTU Industry Internship – IntelliForge AI Programme"
    courses = requests.get(f"{base}/api/courses", timeout=30).json().get("courses", [])
    if course not in courses:
        print(
            f"Course not available on server: {course!r}\n"
            f"Add it via admin API or use a course from: {courses[:5]}…",
            file=sys.stderr,
        )
        sys.exit(1)

    body = {
        "participant_name": "Aayush Kulkarni",
        "course_name": course,
        "completion_date": "2026-06-10",
        "instructor_name": "IntelliForge Program Lead",
        "certificate_kind": "internship",
        "usn": "1RV22CS014",
        "internship_duration": "January 2026 – June 2026",
        "internship_hours": "120",
        "mentor_name": "Industry Mentor Name",
        "institution_name": "Affiliated Engineering College (VTU)",
    }
    r = requests.post(f"{base}/api/certificate", json=body, timeout=60)
    if r.status_code != 200:
        print(r.status_code, r.text, file=sys.stderr)
        sys.exit(1)
    data = r.json()
    print("certificate_id:", data.get("certificate_id"))
    print("verify URL:     ", data.get("url"))

    pdf = requests.get(data["download_url"], timeout=60)
    if pdf.status_code != 200:
        print("PDF download failed", pdf.status_code, file=sys.stderr)
        sys.exit(1)
    path = args.out
    with open(path, "wb") as f:
        f.write(pdf.content)
    print("saved PDF to:  ", path)


if __name__ == "__main__":
    main()
