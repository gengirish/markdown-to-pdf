"""Idempotent single issuance.

The gap this closes: `index.py`'s CORS config advertises `Idempotency-Key` as an
allowed header, so a careful client sends it on `/api/v1` issuance and believes
it is protected. It was not. A network retry minted a second credential and
consumed quota twice.

Every test here was verified by breaking the guard it covers and watching it
fail — a test that has never been seen to fail is a comment.

Expiry is exercised by injecting the clock, never by sleeping: `IdempotencyStore`
takes `clock=`, and the module-level `issuance_store` has its clock swapped for
the one test that needs time to move.
"""

import pytest

from api.core.idempotency import (
    IdempotencyConflict,
    IdempotencyStore,
    fingerprint,
    issuance_store,
)
from api.models.organization import Organization
from api.models.usage import UsageLedger
from api.services.issuance import (
    IssuanceError,
    IssueRequest,
    issue_credential,
)


@pytest.fixture(autouse=True)
def clean_store():
    """Nothing leaks between tests — the store outlives a request by design."""
    issuance_store.clear()
    yield
    issuance_store.clear()


def an_org(db_session, slug, quota=100):
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org is None:
        org = Organization(
            slug=slug, name=slug.title(), tier="community", monthly_quota=quota
        )
        db_session.add(org)
        db_session.commit()
    # Each test starts from a known meter reading regardless of order.
    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    if ledger is not None:
        db_session.delete(ledger)
        db_session.commit()
    return org


def used(db_session, org):
    db_session.expire_all()
    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    return ledger.credentials_issued if ledger else 0


def a_request(name="Ada Lovelace", key="retry-me", **kw):
    return IssueRequest(
        recipient_name=name,
        title="Analytical Engines",
        recipient_email=f"{name.split()[0].lower()}@example.com",
        idempotency_key=key,
        **kw,
    )


# ---------------------------------------------------------------------------
# The service layer
# ---------------------------------------------------------------------------


def test_replay_returns_the_original_credential(db_session):
    org = an_org(db_session, "idem-replay")

    first = issue_credential(org.slug, a_request())
    second = issue_credential(org.slug, a_request())

    assert second.public_id == first.public_id
    assert second.verify_url == first.verify_url


def test_replay_does_not_consume_quota_again(db_session):
    org = an_org(db_session, "idem-quota")

    issue_credential(org.slug, a_request())
    assert used(db_session, org) == 1

    issue_credential(org.slug, a_request())
    issue_credential(org.slug, a_request())

    # Three calls, one key, one unit of quota. Before this change the meter
    # read 3 and there were three rows.
    assert used(db_session, org) == 1


def test_two_orgs_may_use_the_same_key(db_session):
    """Scope is the org slug. A shared key must not cross a tenant boundary."""
    left = an_org(db_session, "idem-tenant-a")
    right = an_org(db_session, "idem-tenant-b")

    a = issue_credential(left.slug, a_request(name="Ada Lovelace", key="shared"))
    b = issue_credential(right.slug, a_request(name="Grace Hopper", key="shared"))

    assert a.public_id != b.public_id
    assert b.recipient_name == "Grace Hopper"
    assert used(db_session, left) == 1
    assert used(db_session, right) == 1


def test_same_key_different_payload_is_a_conflict(db_session):
    """409, not a silent replay — the caller would otherwise never learn that
    their second recipient was never issued anything."""
    org = an_org(db_session, "idem-conflict")

    issue_credential(org.slug, a_request(name="Ada Lovelace", key="oops"))

    with pytest.raises(IssuanceError) as exc:
        issue_credential(org.slug, a_request(name="Grace Hopper", key="oops"))

    assert exc.value.code == 409
    # The conflicting request did not issue anything and did not meter.
    assert used(db_session, org) == 1


def test_expired_entry_mints_a_new_credential(db_session, monkeypatch):
    """TTL is honoured, tested by moving the clock rather than by sleeping."""
    org = an_org(db_session, "idem-expiry")

    now = [1_000_000.0]
    monkeypatch.setattr(issuance_store, "_clock", lambda: now[0])

    first = issue_credential(org.slug, a_request(key="ttl"))

    now[0] += 3599  # still inside the 1h window
    assert issue_credential(org.slug, a_request(key="ttl")).public_id == first.public_id
    assert used(db_session, org) == 1

    now[0] += 2  # past it
    third = issue_credential(org.slug, a_request(key="ttl"))
    assert third.public_id != first.public_id
    assert used(db_session, org) == 2


def test_no_key_behaves_exactly_as_before(db_session):
    org = an_org(db_session, "idem-nokey")

    a = issue_credential(org.slug, a_request(key=None))
    b = issue_credential(org.slug, a_request(key=None))
    c = issue_credential(org.slug, a_request(key=""))

    assert len({a.public_id, b.public_id, c.public_id}) == 3
    assert used(db_session, org) == 3


# ---------------------------------------------------------------------------
# The store on its own
# ---------------------------------------------------------------------------


def test_store_expiry_uses_the_injected_clock():
    now = [0.0]
    store = IdempotencyStore(ttl_seconds=10, clock=lambda: now[0])
    fp = fingerprint({"a": 1})

    store.store("org", "k", fp, "result")
    assert store.lookup("org", "k", fp) == "result"

    now[0] = 9.9
    assert store.lookup("org", "k", fp) == "result"

    now[0] = 10.0
    assert store.lookup("org", "k", fp) is None


def test_store_conflict_raises():
    store = IdempotencyStore()
    store.store("org", "k", fingerprint({"a": 1}), "first")

    with pytest.raises(IdempotencyConflict):
        store.lookup("org", "k", fingerprint({"a": 2}))


def test_store_scopes_are_independent():
    store = IdempotencyStore()
    fp = fingerprint({"a": 1})
    store.store("org-a", "k", fp, "a-result")

    assert store.lookup("org-b", "k", fp) is None
    assert store.lookup("org-a", "k", fp) == "a-result"


def test_fingerprint_ignores_dict_ordering():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_sweep_drops_expired_entries_when_the_store_grows():
    now = [0.0]
    store = IdempotencyStore(ttl_seconds=10, max_entries=5, clock=lambda: now[0])
    fp = fingerprint({"x": 1})

    for i in range(5):
        store.store("org", f"old-{i}", fp, i)

    now[0] = 100.0
    for i in range(2):
        store.store("org", f"new-{i}", fp, i)

    assert store.lookup("org", "old-0", fp) is None
    assert store.lookup("org", "new-0", fp) == 0
