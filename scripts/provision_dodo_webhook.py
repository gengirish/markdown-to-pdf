#!/usr/bin/env python
"""Register the Dodo webhook endpoint and print its signing key.

The other half of D0. `provision_dodo_products.py` makes the thing a customer
buys; this makes the delivery that tells us they bought it. Without it a
payment succeeds and the org stays on Community, which is the failure this
codebase keeps producing: two halves each correct, nothing joining them.

    export DODO_PAYMENTS_API_KEY=...
    python scripts/provision_dodo_webhook.py --live            # what it would do
    python scripts/provision_dodo_webhook.py --apply --live    # do it

It prints the signing key, which is a **secret**: it is what proves a delivery
came from Dodo. Put it straight into `fly secrets set` (the script prints the
line) and do not paste it anywhere else.

The endpoint is registered at the API host, `api.certforge.intelliforge.tech`,
never the dashboard host — that one reaches Fly directly, so no Vercel rewrite
sits between Dodo and the handler.

It subscribes to `subscription.*` only. `routes/billing.py` reconciles those by
reading the subscription's state; payments, refunds and disputes move no tier,
so delivering them would only add retries to ignore.
"""

from __future__ import annotations

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WEBHOOK_URL = "https://api.certforge.intelliforge.tech/api/v1/webhooks/dodo"

#: Every event the handler acts on. Dodo's own names, not ours.
EVENT_TYPES = [
    "subscription.active",
    "subscription.renewed",
    "subscription.on_hold",
    "subscription.paused",
    "subscription.unpaused",
    "subscription.past_due",
    "subscription.cancelled",
    "subscription.failed",
    "subscription.expired",
    "subscription.plan_changed",
]


def _client(live: bool):
    try:
        from dodopayments import DodoPayments
    except ImportError:
        sys.exit("dodopayments is not installed — pip install -r apps/api/requirements.txt")

    key = os.environ.get("DODO_PAYMENTS_API_KEY", "").strip()
    if not key:
        sys.exit("DODO_PAYMENTS_API_KEY is not set.")
    return DodoPayments(bearer_token=key, environment="live_mode" if live else "test_mode")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually register the endpoint (default: print the plan)")
    parser.add_argument("--live", action="store_true",
                        help="live mode. Without this, test mode, whatever the key is")
    args = parser.parse_args()

    client = _client(args.live)
    mode = "live_mode" if args.live else "test_mode"
    print(f"Dodo {mode}; {'applying' if args.apply else 'dry run'}\n")

    try:
        existing = list(client.webhooks.list())
    except Exception as exc:  # noqa: BLE001 — the SDK's error types vary by version
        if "401" in str(exc) or "Unauthorized" in str(exc):
            sys.exit(
                "Dodo rejected the key (401). A key belongs to one mode: a live key "
                "cannot read test mode, and vice versa. Re-run with --live if this is "
                "a live key."
            )
        raise

    found = next((w for w in existing if getattr(w, "url", None) == WEBHOOK_URL), None)

    if found is None:
        if not args.apply:
            print(f"create  {WEBHOOK_URL}")
            print(f"        events: {', '.join(EVENT_TYPES)}  (dry run)")
            return 0
        found = client.webhooks.create(
            url=WEBHOOK_URL,
            description="CertForge: subscription state -> organization tier",
            filter_types=EVENT_TYPES,
        )
        print(f"created {WEBHOOK_URL}")
    else:
        print(f"exists  {WEBHOOK_URL}")

    webhook_id = getattr(found, "id", None) or getattr(found, "webhook_id", None)
    print(f"        id: {webhook_id}")

    # Fetched rather than read off the create response: an endpoint that
    # already existed carries no secret in its listing, and the whole point of
    # this script is to hand over a key that works either way.
    secret = client.webhooks.retrieve_secret(webhook_id)
    value = getattr(secret, "secret", None) or secret

    print("\nThis next line contains a secret. Run it, then clear your scrollback:\n")
    print(f"fly secrets set --app certforge-api DODO_PAYMENTS_WEBHOOK_KEY={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
