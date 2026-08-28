"""Bulk issuance: the meter, and the job that must exist.

`POST /orgs/{slug}/credentials/bulk` had no happy-path coverage at all — the
only bulk test in the suite posted an invalid template id and stopped there.
Two defects lived behind that gap, and both are the same shape as the email
delivery bug: an outcome that leaves no way to tell it apart from success.

  QUOTA    the route read UsageLedger to reject an over-quota upload and never
           wrote it back, so bulk was unmetered while single issuance metered
           correctly. Fifty credentials against a fifty quota left the counter
           at zero.

  ENQUEUE  the Procrastinate job was dispatched with a bare
           asyncio.create_task after the commit. If that failed — swallowed
           exception, garbage-collected task, or a machine that scaled to zero
           first — the batch row committed anyway with status="pending" and no
           job. Nothing reconciles that. There is no reaper.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.core.principal import LIVE_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import Credential, CredentialBatch
from api.models.organization import Organization
from api.models.template import Template
from api.models.usage import UsageLedger

#: Patched everywhere it is used. The real one talks to Procrastinate, which
#: needs the Postgres the test suite deliberately does not have.
DEFER = "api.routes.studio.process_batch.defer_async"


def org_with_key(db_session, slug, raw_key, quota):
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org is None:
        org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=quota)
        db_session.add(org)
        db_session.commit()
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
        db_session.commit()
    return org


def a_template(db_session, org):
    tpl = db_session.query(Template).filter_by(org_id=org.id).first()
    if tpl is None:
        tpl = Template(
            org_id=org.id,
            name="Bulk Test Template",
            html_source="<html><body>{{name}} — {{title}}</body></html>",
        )
        db_session.add(tpl)
        db_session.commit()
    return tpl


def csv_bytes(*names):
    lines = ["name,title,email"]
    lines += [f"{n},Analytical Engines,{n.lower()}@example.com" for n in names]
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload(client, slug, raw, template_id, *names):
    return client.post(
        f"/api/v1/orgs/{slug}/credentials/bulk",
        headers={"Authorization": f"Bearer {raw}"},
        data={"template_id": str(template_id)},
        files={"file": ("people.csv", csv_bytes(*names), "text/csv")},
    )


def ledger_for(db_session, org):
    return (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )


# -- the meter ----------------------------------------------------------------

def test_a_bulk_upload_consumes_quota(client, db_session):
    """It used to read the ledger and never write it."""
    raw = LIVE_PREFIX + "bulk-meter-key"
    org = org_with_key(db_session, "bulk-meter", raw, quota=10)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock):
        r = upload(client, "bulk-meter", raw, tpl.id, "Ada", "Grace", "Katherine")
    assert r.status_code == 200, r.text

    db_session.expire_all()
    ledger = ledger_for(db_session, org)
    assert ledger is not None, "no ledger row was written at all"
    assert ledger.credentials_issued == 3


def test_the_quota_actually_binds_across_two_uploads(client, db_session):
    """The regression: unmetered bulk let you spend the same quota forever."""
    raw = LIVE_PREFIX + "bulk-binds-key"
    org = org_with_key(db_session, "bulk-binds", raw, quota=4)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock):
        first = upload(client, "bulk-binds", raw, tpl.id, "Ada", "Grace", "Katherine")
        assert first.status_code == 200, first.text

        # 3 of 4 spent. Two more must not fit.
        second = upload(client, "bulk-binds", raw, tpl.id, "Dorothy", "Mary")

    assert second.status_code == 402, second.text

    db_session.expire_all()
    assert ledger_for(db_session, org).credentials_issued == 3, "the refused upload still spent quota"


def test_bulk_and_single_issuance_share_one_meter(client, db_session):
    """They disagreed: single wrote the ledger, bulk did not."""
    raw = LIVE_PREFIX + "bulk-shared-key"
    org = org_with_key(db_session, "bulk-shared", raw, quota=3)
    tpl = a_template(db_session, org)

    single = client.post(
        "/api/v1/orgs/bulk-shared/credentials",
        headers={"Authorization": f"Bearer {raw}"},
        json={"recipient_name": "Ada Lovelace", "title": "Analytical Engines"},
    )
    assert single.status_code == 201, single.text

    with patch(DEFER, new_callable=AsyncMock):
        # 1 spent singly; a 3-row bulk cannot fit in the remaining 2.
        r = upload(client, "bulk-shared", raw, tpl.id, "Grace", "Katherine", "Dorothy")
    assert r.status_code == 402, "bulk did not see the credential single issuance spent"

    with patch(DEFER, new_callable=AsyncMock):
        fits = upload(client, "bulk-shared", raw, tpl.id, "Grace", "Katherine")
    assert fits.status_code == 200, fits.text

    db_session.expire_all()
    assert ledger_for(db_session, org).credentials_issued == 3


# -- the job ------------------------------------------------------------------

def test_a_committed_batch_always_has_a_queued_job(client, db_session):
    raw = LIVE_PREFIX + "bulk-queued-key"
    org = org_with_key(db_session, "bulk-queued", raw, quota=10)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock) as defer:
        r = upload(client, "bulk-queued", raw, tpl.id, "Ada", "Grace")
    assert r.status_code == 200, r.text

    batch_id = r.json()["data"]["batch_id"]
    defer.assert_awaited_once_with(batch_id_str=batch_id)


def test_a_failed_enqueue_leaves_no_batch_behind(client, db_session):
    """The defect this exists for.

    A committed batch with no job sits at "pending" forever, and nothing can
    tell it apart from one about to start — same ambiguity as a silently
    skipped email. Rolling back is what makes the failure visible and
    retryable.
    """
    raw = LIVE_PREFIX + "bulk-rollback-key"
    org = org_with_key(db_session, "bulk-rollback", raw, quota=10)
    tpl = a_template(db_session, org)

    before = db_session.query(CredentialBatch).filter_by(org_id=org.id).count()

    with patch(DEFER, new_callable=AsyncMock) as defer:
        defer.side_effect = RuntimeError("procrastinate connector is closed")
        with pytest.raises(RuntimeError):
            upload(client, "bulk-rollback", raw, tpl.id, "Ada", "Grace")

    db_session.expire_all()
    after = db_session.query(CredentialBatch).filter_by(org_id=org.id).count()
    assert after == before, "a batch was committed with no job to run it"


def test_a_failed_enqueue_does_not_spend_quota(client, db_session):
    """The rollback has to take the meter with it, or a failed upload bills."""
    raw = LIVE_PREFIX + "bulk-nospend-key"
    org = org_with_key(db_session, "bulk-nospend", raw, quota=10)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock) as defer:
        defer.side_effect = RuntimeError("procrastinate connector is closed")
        with pytest.raises(RuntimeError):
            upload(client, "bulk-nospend", raw, tpl.id, "Ada", "Grace")

    db_session.expire_all()
    ledger = ledger_for(db_session, org)
    assert ledger is None or ledger.credentials_issued == 0


def test_a_failed_enqueue_leaves_no_orphan_credentials(client, db_session):
    raw = LIVE_PREFIX + "bulk-nocreds-key"
    org = org_with_key(db_session, "bulk-nocreds", raw, quota=10)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock) as defer:
        defer.side_effect = RuntimeError("procrastinate connector is closed")
        with pytest.raises(RuntimeError):
            upload(client, "bulk-nocreds", raw, tpl.id, "Ada", "Grace")

    db_session.expire_all()
    assert db_session.query(Credential).filter_by(org_id=org.id).count() == 0


# -- what the batch row records -----------------------------------------------

def test_the_batch_records_its_rows_as_pending_credentials(client, db_session):
    raw = LIVE_PREFIX + "bulk-rows-key"
    org = org_with_key(db_session, "bulk-rows", raw, quota=10)
    tpl = a_template(db_session, org)

    with patch(DEFER, new_callable=AsyncMock):
        r = upload(client, "bulk-rows", raw, tpl.id, "Ada", "Grace", "Katherine")
    assert r.status_code == 200, r.text

    data = r.json()["data"]
    assert data["total"] == 3
    assert data["status"] == "pending"

    db_session.expire_all()
    import uuid as _uuid

    creds = (
        db_session.query(Credential)
        .filter_by(batch_id=_uuid.UUID(data["batch_id"]))
        .all()
    )
    assert len(creds) == 3
    assert {c.status for c in creds} == {"pending"}
    assert {c.recipient_name for c in creds} == {"Ada", "Grace", "Katherine"}
