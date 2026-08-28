"""The HTTP wiring between the issuing route and the two new guards.

The service layer and the limiter each have their own suites. This file covers
only the seam between them and `routes/credentials.py` — the part no agent
owned, and the part that is easy to leave dangling: a header nothing reads, or
a dependency nothing declares, both look exactly like working code.

That is not hypothetical here. `Idempotency-Key` sat in the CORS allow-list for
months with nothing reading it, so a client could send it, believe a retry was
safe, and get a duplicate credential plus a second quota charge.
"""

import pytest

from api.core.principal import LIVE_PREFIX, hash_api_key
from api.core.rate_limit import default_limiter
from api.models.api_key import ApiKey
from api.models.organization import Organization
from api.models.usage import UsageLedger


@pytest.fixture(autouse=True)
def _clean_buckets():
    """The limiter is process-wide, so one test's traffic is another's budget.

    Without this the suite would pass or fail depending on test order, which is
    the worst kind of red: real, intermittent, and blamed on flakiness.
    """
    default_limiter.reset()
    yield
    default_limiter.reset()


def org_with_key(db_session, slug, raw_key, quota=500):
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org is None:
        org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=quota)
        db_session.add(org)
        db_session.commit()
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
        db_session.commit()
    return org


def issue(client, slug, raw, *, key=None, name="Ada Lovelace", title="Analytical Engines"):
    headers = {"Authorization": f"Bearer {raw}"}
    if key:
        headers["Idempotency-Key"] = key
    return client.post(
        f"/api/v1/orgs/{slug}/credentials",
        headers=headers,
        json={"recipient_name": name, "title": title},
    )


def used(db_session, org):
    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    return ledger.credentials_issued if ledger else 0


# -- Idempotency-Key actually reaches the service -----------------------------

def test_the_header_is_read_and_a_retry_returns_the_original(client, db_session):
    raw = LIVE_PREFIX + "hdr-replay-key"
    org_with_key(db_session, "hdr-replay", raw)

    first = issue(client, "hdr-replay", raw, key="retry-me")
    second = issue(client, "hdr-replay", raw, key="retry-me")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_a_retry_through_the_route_does_not_charge_quota_twice(client, db_session):
    raw = LIVE_PREFIX + "hdr-quota-key"
    org = org_with_key(db_session, "hdr-quota", raw)

    issue(client, "hdr-quota", raw, key="charge-once")
    issue(client, "hdr-quota", raw, key="charge-once")

    db_session.expire_all()
    assert used(db_session, org) == 1


def test_the_same_key_with_a_different_body_is_a_409(client, db_session):
    """The route forwards IssuanceError.code, so this only passes if the
    service's 409 survives the HTTP layer."""
    raw = LIVE_PREFIX + "hdr-conflict-key"
    org = org_with_key(db_session, "hdr-conflict", raw)

    issue(client, "hdr-conflict", raw, key="reused", name="Ada Lovelace")
    clash = issue(client, "hdr-conflict", raw, key="reused", name="Grace Hopper")

    assert clash.status_code == 409, clash.text

    # A refused call must not bill. Only the first issuance counted.
    db_session.expire_all()
    assert used(db_session, org) == 1


def test_without_the_header_every_call_issues(client, db_session):
    """The guard is opt-in — no header must behave exactly as it always did."""
    raw = LIVE_PREFIX + "hdr-none-key"
    org_with_key(db_session, "hdr-none", raw)

    first = issue(client, "hdr-none", raw)
    second = issue(client, "hdr-none", raw)

    assert first.json()["data"]["id"] != second.json()["data"]["id"]


# -- the limiter is actually attached to the route ----------------------------

def test_the_route_reports_the_callers_budget(client, db_session):
    raw = LIVE_PREFIX + "hdr-budget-key"
    org_with_key(db_session, "hdr-budget", raw)

    r = issue(client, "hdr-budget", raw)
    assert r.status_code == 201, r.text
    # Present only if the dependency is declared on the route — a limiter that
    # exists but is wired to nothing looks identical without this.
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers


def test_the_budget_falls_as_it_is_spent(client, db_session):
    raw = LIVE_PREFIX + "hdr-spend-key"
    org_with_key(db_session, "hdr-spend", raw)

    first = int(issue(client, "hdr-spend", raw).headers["X-RateLimit-Remaining"])
    second = int(issue(client, "hdr-spend", raw).headers["X-RateLimit-Remaining"])
    assert second == first - 1


def test_exceeding_the_budget_is_refused_in_the_v1_envelope(client, db_session):
    """Spends a whole window deliberately, so the 429 under test is the one
    production emits rather than one synthesised by the limiter's own suite."""
    from api.core.config import API_V1_RATE_LIMIT

    raw = LIVE_PREFIX + "hdr-refuse-key"
    org_with_key(db_session, "hdr-refuse", raw, quota=API_V1_RATE_LIMIT + 10)

    last = None
    for _ in range(API_V1_RATE_LIMIT + 1):
        last = issue(client, "hdr-refuse", raw)

    assert last.status_code == 429, last.text
    body = last.json()
    assert body["success"] is False
    assert body["error"]["type"] == "rate_limit_exceeded"
    assert "Retry-After" in last.headers


def test_a_refused_call_does_not_consume_quota(client, db_session):
    """The limiter runs as a dependency, so it must reject before the handler
    reaches consume_quota — otherwise being throttled would still bill."""
    from api.core.config import API_V1_RATE_LIMIT

    raw = LIVE_PREFIX + "hdr-nobill-key"
    org = org_with_key(db_session, "hdr-nobill", raw, quota=API_V1_RATE_LIMIT + 10)

    for _ in range(API_V1_RATE_LIMIT + 1):
        issue(client, "hdr-nobill", raw)

    db_session.expire_all()
    assert used(db_session, org) == API_V1_RATE_LIMIT


def test_two_organizations_do_not_share_a_budget(client, db_session):
    """Keyed on the principal, not the process. One busy integration must not
    throttle everyone else on the machine."""
    from api.core.config import API_V1_RATE_LIMIT

    noisy = LIVE_PREFIX + "hdr-noisy-key"
    quiet = LIVE_PREFIX + "hdr-quiet-key"
    org_with_key(db_session, "hdr-noisy", noisy, quota=API_V1_RATE_LIMIT + 10)
    org_with_key(db_session, "hdr-quiet", quiet)

    for _ in range(API_V1_RATE_LIMIT + 1):
        issue(client, "hdr-noisy", noisy)

    assert issue(client, "hdr-quiet", quiet).status_code == 201
