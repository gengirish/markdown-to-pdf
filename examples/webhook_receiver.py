#!/usr/bin/env python3
"""Sample FastAPI receiver for IntelliForge certificate.created webhook callbacks.

Requires: pip install fastapi uvicorn
Run: python webhook_receiver.py  (listens on port 9000)

Point callback_url at http://<your-host>:9000/webhook when creating certificates.
Downstream: forward payload to Slack, email, or CRM from handle_certificate_created().
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_receiver")

app = FastAPI(title="IntelliForge Webhook Demo", version="1.0.0")


def handle_certificate_created(data: dict[str, Any]) -> None:
    """Hook for Slack webhooks, AgentMail, Salesforce, etc."""
    # Example: logger.info("Would notify Slack: %s", data.get("url"))
    _ = data  # replace with real integrations


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    event = payload.get("event")
    if event == "certificate.created":
        data = payload.get("data") or {}
        logger.info("certificate.created: %s", data)
        handle_certificate_created(data)
    else:
        logger.info("Ignored event: %s", event)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
