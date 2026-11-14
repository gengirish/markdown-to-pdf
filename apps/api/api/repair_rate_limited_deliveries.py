"""Move credentials that failed on the provider's daily limit to `deferred`.

Before deferred delivery existed, a send AgentMail refused for volume was
recorded as `failed` and cost an attempt, as did its automatic retry seconds
later. On 2026-11-12 that left 44 rows at `failed` with 2 of 3 attempts used.
Nobody was mailed. This hands those rows to the deferred-send sweep, which
sends them once the gate is open, oldest first, stopping at the next refusal.

Runs on Fly, where DATABASE_URL lives:

    fly ssh console -a certforge-api -C "python -m api.repair_rate_limited_deliveries"
    fly ssh console -a certforge-api -C "python -m api.repair_rate_limited_deliveries --apply"
    ... --org navodaya-vidyalaya-alumni-1793974077657581307   # one org only

Without --apply it lists what it would change and rolls back.

`delivery_attempts` is left exactly as it is. The error column keeps only the
last refusal, so how many of a row's attempts were refusals for volume cannot
be proved, and this codebase does not backfill what it cannot prove. With 2
of 3 used, a later accepted send takes the row to 3, which is fine: it was
delivered.

Safe to repeat: a second run finds no `failed` rows with that error left.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from api.models.credential import DELIVERY_DEFERRED, DELIVERY_FAILED, REVOKED, Credential
from api.models.organization import Organization

#: The provider's words, as `agentmail_deliver` stored them. Matched as a
#: prefix so the "Share the credential link instead." suffix is irrelevant.
LIMIT_ERROR_PREFIX = "Daily send limit exceeded"


def candidates(session: Session, org_slug: Optional[str] = None) -> list[Credential]:
    query = session.query(Credential).filter(
        Credential.delivery_status == DELIVERY_FAILED,
        Credential.delivery_error.like(f"{LIMIT_ERROR_PREFIX}%"),
        Credential.status != REVOKED,
    )
    if org_slug:
        org = session.query(Organization).filter_by(slug=org_slug).first()
        if org is None:
            raise SystemExit(f"No organization {org_slug!r}.")
        query = query.filter(Credential.org_id == org.id)
    rows = query.order_by(Credential.issued_at.asc()).all()
    # A cf_test_ key never emails; its rows cannot be here, but a row that
    # somehow is must not be handed to a sender.
    return [c for c in rows if not (c.metadata_ or {}).get("_test")]


def repair(session: Session, org_slug: Optional[str] = None,
           now: Optional[datetime] = None) -> list[Credential]:
    """Defer every candidate, due now, inside the caller's transaction."""
    now = now or datetime.now(timezone.utc)
    rows = candidates(session, org_slug)
    for cred in rows:
        cred.delivery_status = DELIVERY_DEFERRED
        cred.delivery_next_attempt_at = now
        cred.delivery_error = (
            f"{LIMIT_ERROR_PREFIX}. Recorded as failed before deferred delivery "
            f"existed; queued to send by the repair of {now:%Y-%m-%d}."
        )
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--org", help="limit to one org slug")
    parser.add_argument("--apply", action="store_true",
                        help="commit the change (default: list it and roll back)")
    args = parser.parse_args(argv)

    from api.models import get_session_factory

    session = get_session_factory()()
    try:
        rows = repair(session, args.org)
        for cred in rows:
            print(f"{cred.public_id}  attempts={cred.delivery_attempts}  {cred.recipient_email}")
        print(f"{len(rows)} credential(s) moved to deferred.")
        if args.apply:
            session.commit()
            print("Committed. The sweep sends them once the gate is open, oldest first.")
        else:
            session.rollback()
            print("Dry run — rolled back. Re-run with --apply to commit.")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
