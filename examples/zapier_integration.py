#!/usr/bin/env python3
"""Flask endpoint for Zapier (Catch Hook → Webhooks by Zapier) to mint certificates.

Zapier sends form fields; we POST to IntelliForge and return JSON Zapier can map to next steps.

Requires: pip install flask httpx
Env: INTELLIFORGE_URL, INTELLIFORGE_API_KEY
Run: flask --app zapier_integration run -p 8080
  Or: python zapier_integration.py
"""

from __future__ import annotations

import os

import httpx
from flask import Flask, jsonify, request

BASE_URL = os.environ.get("INTELLIFORGE_URL", "https://certs.intelliforge.tech").rstrip("/")
API_KEY = os.environ.get("INTELLIFORGE_API_KEY", "").strip()

app = Flask(__name__)


@app.post("/zapier/certificate")
def zapier_certificate():
    """Expect form fields: participant_name, course_name, completion_date; optional instructor_name, participant_email."""
    participant_name = request.form.get("participant_name", "").strip()
    course_name = request.form.get("course_name", "").strip()
    completion_date = request.form.get("completion_date", "").strip()
    if not participant_name or not course_name or not completion_date:
        return jsonify({"ok": False, "error": "participant_name, course_name, completion_date required"}), 400

    payload = {
        "participant_name": participant_name,
        "course_name": course_name,
        "completion_date": completion_date,
        "instructor_name": request.form.get("instructor_name") or "IntelliForge AI Team",
        "participant_email": (request.form.get("participant_email") or "").strip(),
    }
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=60.0) as client:
        r = client.post("/api/certificate", json=payload)
        if r.status_code >= 400:
            return jsonify({"ok": False, "status": r.status_code, "error": r.text}), r.status_code
        data = r.json()

    # Fields Zapier can pick up in the next action (URL shortener, Slack, Sheets, etc.)
    return jsonify(
        {
            "ok": True,
            "certificate_url": data.get("url"),
            "download_url": data.get("download_url"),
            "certificate_id": data.get("certificate_id"),
            "token": data.get("token"),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
