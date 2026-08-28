"""Prepare a throwaway database for the Playwright suite.

Run from `apps/api` with `DATABASE_URL` pointing at the SQLite file the E2E API
server will use. `playwright.config.js` chains this ahead of uvicorn so the
ordering is guaranteed — a global setup step would race the web server.

Why SQLite rather than the real Postgres: E2E must run on a laptop and in CI
without provisioning anything. `api/models/__init__.py` now picks connect args
by dialect, so the same application code serves both.

The API key below is a fixed constant shared with the specs. That is safe
precisely because this database is disposable and local; do not copy the pattern
anywhere a real key belongs.
"""

import os
import sys

# `python e2e/seed_e2e.py` from apps/api needs the app importable.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../apps/api")

E2E_ORG_SLUG = "e2e-org"
E2E_ORG_NAME = "E2E Test College"
E2E_API_KEY = "cf_live_e2e-fixed-key-local-only"


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL must be set before seeding the E2E database")

    from api.models import Base, get_engine, get_db
    from api.models.api_key import ApiKey
    from api.models.organization import Organization
    from api.core.principal import hash_api_key

    Base.metadata.create_all(bind=get_engine())

    # Global templates, so issuance can resolve a default without one being
    # named. Best-effort: a failure here should not stop the suite from running
    # the parts that do not need a template.
    try:
        from api.seed import seed

        seed()
    except Exception as exc:  # noqa: BLE001 — reported, not fatal
        print(f"[seed_e2e] template seed skipped: {exc}")

    with get_db() as session:
        org = session.query(Organization).filter_by(slug=E2E_ORG_SLUG).first()
        if org is None:
            org = Organization(
                slug=E2E_ORG_SLUG,
                name=E2E_ORG_NAME,
                tier="community",
                monthly_quota=10_000,
                # Branding is deliberately set: the viewer must be seen to use
                # the organization's colours, not the global env fallback.
                primary_color="#12124a",
                accent_color="#d4af37",
                footer_text="Issued by E2E Test College",
            )
            session.add(org)
            session.flush()

        if session.query(ApiKey).filter_by(org_id=org.id).first() is None:
            session.add(
                ApiKey(
                    org_id=org.id,
                    key_hash=hash_api_key(E2E_API_KEY),
                    label="e2e",
                )
            )

    print(f"[seed_e2e] ready: org={E2E_ORG_SLUG}")


if __name__ == "__main__":
    main()
