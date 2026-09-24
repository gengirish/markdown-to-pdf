"""A batch must never hang at "0 of N" with nothing left to run it.

Two production shapes of that hang, both silent from the dashboard:

  RACE     The upload route defers the job inside its transaction, and
           Procrastinate commits the job on its own connection. The worker —
           in the same process, woken by NOTIFY — could read the batch before
           the route committed it, log "not found", and finish the job as a
           success. The batch then committed as pending with no job.

  STALLED  A deploy or an idle stop killed the machine mid-batch. The job sat
           in `doing` under a worker that no longer existed, the batch sat in
           `processing`, and even a retried job refused a batch that was not
           `pending`.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from api.core import worker
from api.core.principal import LIVE_PREFIX
from api.models.credential import Credential, CredentialBatch

from test_bulk_issuance import DEFER, a_template, org_with_key, upload  # noqa: E402


def staged_batch(client, db_session, slug, *names):
    raw = LIVE_PREFIX + f"{slug}-key"
    org = org_with_key(db_session, slug, raw, quota=100)
    tpl = a_template(db_session, org)
    with patch(DEFER, new_callable=AsyncMock):
        r = upload(client, slug, raw, tpl.id, *names)
    assert r.status_code == 200, r.text
    return db_session.get(CredentialBatch, uuid.UUID(r.json()["data"]["batch_id"]))


# -- RACE ---------------------------------------------------------------------

def test_an_invisible_batch_is_reported_as_not_yet_rather_than_done():
    """None — "try again" — is what separates the race from a finished batch.
    This returned [] for both, and the job ended as a success."""
    assert worker._process_batch_sync(uuid.uuid4()) is None


def test_the_task_waits_for_a_batch_that_is_not_committed_yet(monkeypatch):
    monkeypatch.setattr(worker, "BATCH_VISIBLE_WAIT_SECONDS", 0)
    results = iter([None, None, []])
    calls = []

    def fake(batch_id):
        calls.append(batch_id)
        return next(results)

    monkeypatch.setattr(worker, "_process_batch_sync", fake)
    asyncio.run(worker.process_batch.func(batch_id_str=str(uuid.uuid4())))
    assert len(calls) == 3


# -- claiming -----------------------------------------------------------------

def test_a_second_job_for_the_same_batch_does_not_process_it_again(client, db_session):
    """The recovery sweep may queue a batch that is still legitimately
    waiting. Whichever job claims it second must find it taken."""
    batch = staged_batch(client, db_session, "recover-claim", "Ada")

    worker._process_batch_sync(batch.id)
    with patch.object(worker, "render_credential_pdf") as render:
        assert worker._process_batch_sync(batch.id) == []
    render.assert_not_called()

    db_session.expire_all()
    assert db_session.get(CredentialBatch, batch.id).succeeded == 1


# -- STALLED ------------------------------------------------------------------

def test_a_batch_whose_worker_died_resumes_and_keeps_its_counts(client, db_session):
    """Killed after one row committed: the resumed run processes only the
    rest, and the batch still adds up to what it contains."""
    batch = staged_batch(client, db_session, "recover-stalled", "Ada", "Grace")
    first = (
        db_session.query(Credential)
        .filter_by(batch_id=batch.id)
        .order_by(Credential.recipient_name)
        .first()
    )
    first.status = "issued"
    batch.status = "processing"
    batch.succeeded = 1
    db_session.commit()

    # A retried job alone used to meet "not pending" and return.
    assert worker._process_batch_sync(batch.id) == []
    db_session.expire_all()
    assert db_session.get(CredentialBatch, batch.id).status == "processing"

    worker._release_batch(batch.id)
    worker._process_batch_sync(batch.id)
    db_session.expire_all()

    done = db_session.get(CredentialBatch, batch.id)
    assert done.status == "completed"
    assert done.succeeded == 2
    assert all(
        c.status == "issued"
        for c in db_session.query(Credential).filter_by(batch_id=batch.id)
    )


def test_release_leaves_a_finished_batch_alone(client, db_session):
    batch = staged_batch(client, db_session, "recover-finished", "Ada")
    worker._process_batch_sync(batch.id)

    worker._release_batch(batch.id)
    db_session.expire_all()
    assert db_session.get(CredentialBatch, batch.id).status == "completed"


def test_only_an_old_pending_batch_counts_as_stranded(client, db_session):
    fresh = staged_batch(client, db_session, "recover-fresh", "Ada")
    old = staged_batch(client, db_session, "recover-old", "Grace")
    old.created_at = datetime.now(timezone.utc) - timedelta(
        seconds=worker.STRANDED_BATCH_AFTER_SECONDS + 60
    )
    db_session.commit()

    stranded = worker._stranded_batch_ids()
    assert str(old.id) in stranded
    assert str(fresh.id) not in stranded
