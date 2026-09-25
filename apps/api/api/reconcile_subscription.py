"""Apply a Dodo subscription's current state to its org, as its webhook would have.

For a subscription whose webhook never arrived — no endpoint in that mode, or
a signing key that did not match. Dodo can only resend a delivery it
attempted, so without this a paying org stays on Community until next
month's renewal event. That happened to the first live payment.

Runs on Fly, where DATABASE_URL and the Dodo key live:

    fly ssh console -a certforge-api -C "python -m api.reconcile_subscription sub_…"
    fly ssh console -a certforge-api -C "python -m api.reconcile_subscription sub_… --apply"

Without --apply it runs the real reconcile and rolls it back, so the dry run
reports exactly what --apply would do. It goes through
`billing.reconcile_subscription` — the webhook's own path — so the org is
linked to the subscription (renewals, cancellation and the billing portal all
work afterwards), not merely re-tiered. Setting the tier by hand would leave
the subscription unlinked, and its eventual cancellation would then be
ignored, keeping the org on a paid plan for free.

Safe to repeat: a second run finds the org already governed by this
subscription at this tier and changes nothing.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from api.models.billing_event import BillingEvent
from api.models.organization import Organization
from api.services import billing

#: Recorded in billing_events so a reconciled change is never mistaken for a
#: delivered webhook when someone reads the trail later.
EVENT_TYPE = "manual.reconcile"


def reconcile(
    session: Session, data: dict
) -> tuple[str, Optional[Organization], Optional[str]]:
    """(outcome, org, tier before) for one fetched subscription, inside the
    caller's transaction. The caller decides whether to commit."""
    before = billing._resolve_org(session, data)
    tier_before = before.tier if before is not None else None

    outcome, org = billing.reconcile_subscription(session, data)
    session.add(BillingEvent(
        # Unique per run: the webhook_id column is the replay guard for real
        # deliveries, and a manual run must never collide with one.
        webhook_id=f"reconcile:{data.get('subscription_id')}:{uuid.uuid4().hex}",
        event_type=EVENT_TYPE,
        subscription_id=data.get("subscription_id"),
        org_id=org.id if org is not None else None,
        outcome=outcome,
    ))
    return outcome, org, tier_before


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("subscription_id", help="Dodo subscription id, sub_…")
    parser.add_argument("--apply", action="store_true",
                        help="commit the change (default: run it and roll back)")
    args = parser.parse_args(argv)

    from api.models import get_session_factory

    try:
        data = billing.fetch_subscription(args.subscription_id)
    except (billing.BillingUnavailable, billing.BillingProviderError) as exc:
        print(f"Could not fetch {args.subscription_id} from Dodo: {exc}")
        print("A subscription belongs to one mode: a live one cannot be read with a test key.")
        return 2

    print(f"Dodo says {args.subscription_id} is {data.get('status')!r}, "
          f"product {data.get('product_id')!r}, "
          f"next billing {data.get('next_billing_date')!r}, "
          f"org_id in metadata {(data.get('metadata') or {}).get('org_id')!r}.")

    session = get_session_factory()()
    try:
        outcome, org, tier_before = reconcile(session, data)
        if org is None:
            print(f"Outcome: {outcome}. No organization matches this subscription.")
        else:
            print(f"Outcome: {outcome}. Org {org.slug!r}: tier {tier_before!r} -> {org.tier!r}, "
                  f"subscription status {org.subscription_status!r}.")
        if args.apply:
            session.commit()
            print("Committed.")
        else:
            session.rollback()
            print("Dry run — rolled back. Re-run with --apply to commit.")
    finally:
        session.close()
    return 0 if outcome == billing.APPLIED else 1


if __name__ == "__main__":
    sys.exit(main())
