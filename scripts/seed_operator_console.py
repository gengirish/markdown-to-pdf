"""Seed a LOCAL database with orgs and emails that exercise every state the
operator console (/operator) shows. For reviewing the UI by hand.

    cd apps/api
    DATABASE_URL=sqlite:///operator-demo.sqlite python ../../scripts/seed_operator_console.py

Refuses to run with ENV=production. Idempotent: every row it writes has a
`demo-op-` slug or a `DEMO-OP-` public id, and a re-run deletes those first.
Never point it at a database whose data you care about.

What it creates:
- orgs at 0%, 50%, 85% (amber), 104% (red), on Scale (unlimited, no bar), one
  with an override, two sharing a display name, one on a retired plan name;
- credentials with sent / failed / pending (old and fresh) / unknown /
  not-requested emails, a title that is an email address, and a possible
  duplicate (same name twice in 3 days).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

if os.environ.get("ENV") == "production" or os.environ.get("VERCEL_ENV") == "production":
    sys.exit("Refusing to seed demo data into a production environment.")
if not os.environ.get("DATABASE_URL"):
    sys.exit("Set DATABASE_URL to a local database first.")

from api.models import Base, get_db, get_engine  # noqa: E402
from api.models.credential import Credential  # noqa: E402
from api.models.organization import Organization  # noqa: E402
from api.models.usage import UsageLedger  # noqa: E402

NOW = datetime.now(timezone.utc)

ORGS = [
    # slug, name, tier, override, used this month
    ("demo-op-idle", "Idle Institute", "community", None, 0),
    ("demo-op-half", "Halfway Academy", "community", None, 25),
    ("demo-op-amber", "Amber College", "community", None, 43),
    ("demo-op-red", "Redline Bootcamp", "pro", None, 1040),
    ("demo-op-scale", "Scale University", "scale", None, 3200),
    ("demo-op-override", "Override School", "community", 500, 120),
    ("demo-op-dup-1", "Twin Academy", "community", None, 3),
    ("demo-op-dup-2", "twin academy ", "pro", None, 0),
    ("demo-op-retired", "Legacy Starter Co", "starter", None, 12),
]

CREDS = [
    # org slug, public id, name, email, title, delivery status, age, attempts, error
    ("demo-op-red", "DEMO-OP-SENT", "Asha Rao", "asha@example.com", "Data Science", "sent", timedelta(hours=3), 1, None),
    ("demo-op-red", "DEMO-OP-FAIL", "Vikram Shah", "vikram@example.com", "Data Science", "failed",
     timedelta(hours=5), 1, "AgentMail rejected the request (422): mailbox does not exist"),
    ("demo-op-red", "DEMO-OP-FAIL3", "Meera Iyer", "meera@example.com", "Data Science", "failed",
     timedelta(days=2), 3, "Bounced three times; attempt ceiling reached"),
    ("demo-op-amber", "DEMO-OP-PEND-OLD", "Kiran Das", "kiran@example.com", "Web Dev", "pending", timedelta(hours=4), 1, None),
    ("demo-op-amber", "DEMO-OP-PEND-NEW", "Neha Gupta", "neha@example.com", "Web Dev", "pending", timedelta(minutes=10), 1, None),
    ("demo-op-amber", "DEMO-OP-UNKNOWN", "Old Row", "old@example.com", "Web Dev", "unknown", timedelta(days=60), 0, None),
    ("demo-op-half", "DEMO-OP-TITLE", "Ravi Kumar", "ravi@example.com", "ravi@example.com", "sent", timedelta(days=1), 1, None),
    ("demo-op-half", "DEMO-OP-DUP-A", "Priya Nair", "priya@example.com", "Cloud 101", "sent", timedelta(days=1), 1, None),
    ("demo-op-half", "DEMO-OP-DUP-B", "priya nair", "priya.n@example.com", "Cloud 101", "sent", timedelta(days=4), 1, None),
    ("demo-op-half", "DEMO-OP-NOMAIL", "No Address", "", "Cloud 101", "not_requested", timedelta(days=2), 0,
     "No recipient email on this credential."),
]


def main() -> None:
    Base.metadata.create_all(get_engine())
    period = UsageLedger.current_period()
    with get_db() as session:
        # Explicit, child rows first: SQLite does not cascade without a pragma.
        old_ids = [o.id for o in session.query(Organization.id).filter(Organization.slug.like("demo-op-%"))]
        session.query(Credential).filter(Credential.public_id.like("DEMO-OP-%")).delete(synchronize_session=False)
        if old_ids:
            session.query(UsageLedger).filter(UsageLedger.org_id.in_(old_ids)).delete(synchronize_session=False)
            session.query(Organization).filter(Organization.id.in_(old_ids)).delete(synchronize_session=False)
        session.flush()

        by_slug = {}
        for slug, name, tier, override, used in ORGS:
            org = Organization(slug=slug, name=name, tier=tier, credential_quota_override=override,
                               created_at=NOW - timedelta(days=90))
            session.add(org)
            session.flush()
            by_slug[slug] = org
            if used:
                session.add(UsageLedger(org_id=org.id, period=period, credentials_issued=used))

        for slug, pid, name, email, title, status, age, attempts, error in CREDS:
            session.add(Credential(
                public_id=pid, org_id=by_slug[slug].id, recipient_name=name, recipient_email=email,
                title=title, metadata_={}, hmac_signature="demo", status="issued",
                delivery_status=status, delivery_attempts=attempts, delivery_error=error,
                issued_at=NOW - age, delivered_at=(NOW - age) if status == "sent" else None,
            ))
    print(f"Seeded {len(ORGS)} demo-op- orgs and {len(CREDS)} DEMO-OP- credentials.")


if __name__ == "__main__":
    main()
