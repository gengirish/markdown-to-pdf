"""The credential signature has to mean something.

`credentials.hmac_signature` was written by two code paths and read by none,
and both signed `hmac_sign(public_id)` — the identifier alone. Editing a
credential's recipient name, title, issue date or metadata in the database
left the signature matching, so the column asserted an integrity guarantee it
had never provided.

Every test here fails against that behaviour: with signing and verification
removed, a tampered row renders as a valid credential on all three public
surfaces.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.core.credential_signature import (
    INVALID,
    UNVERIFIED,
    VALID,
    canonical_payload,
    credential_signature_status,
    sign_credential,
)
from api.core.crypto import hmac_sign
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.template import Template


def _org(db_session: Session, slug: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db_session.add(Organization(id=org_id, name=f"Org {slug}", slug=slug))
    db_session.commit()
    return org_id


def _signed_credential(
    db_session: Session,
    public_id: str,
    *,
    slug: str,
    name: str = "Alice Example",
    title: str = "Advanced Widgetry",
    metadata: dict | None = None,
    status: str = "issued",
) -> Credential:
    """A credential written the way the issuance service writes one."""
    cred = Credential(
        public_id=public_id,
        org_id=_org(db_session, slug),
        recipient_name=name,
        recipient_email="alice@example.com",
        title=title,
        metadata_=metadata if metadata is not None else {},
        status=status,
        issued_at=datetime.now(timezone.utc),
    )
    sign_credential(cred)
    db_session.add(cred)
    db_session.commit()
    return cred


def _tamper(db_session: Session, public_id: str, **fields) -> None:
    """Edit a credential behind the API's back, leaving its signature alone."""
    cred = db_session.query(Credential).filter_by(public_id=public_id).first()
    for key, value in fields.items():
        setattr(cred, key, value)
    db_session.commit()


# ── The incident, as a test ────────────────────────────────────────────────


def test_a_tampered_recipient_name_is_refused_by_every_public_surface(
    client: TestClient, db_session
):
    """Rename the recipient in the database and the credential must stop
    verifying — on the viewer, in the badge, and in the PDF alike.

    Before canonical signing all three rendered the new name over the old
    signature, and the signature still matched, because it had only ever
    covered the ID.
    """
    _signed_credential(db_session, "CF-2026-TAMPER01", slug="tamper-name-org")
    _tamper(db_session, "CF-2026-TAMPER01", recipient_name="Mallory Forged")

    page = client.get("/verify/CF-2026-TAMPER01")
    assert page.status_code == 409
    assert "Mallory Forged" not in page.text

    badge = client.get("/credentials/CF-2026-TAMPER01/badge.json")
    assert badge.status_code == 409

    pdf = client.get("/credentials/CF-2026-TAMPER01/pdf")
    assert pdf.status_code == 409

    api = client.get("/api/v1/verify/CF-2026-TAMPER01")
    assert api.status_code == 409
    # The reason has to be machine-readable. `code` is the status number and
    # 409 alone does not say what conflicted.
    assert api.json()["error"]["type"] == "signature_mismatch"


@pytest.mark.parametrize(
    "field,value",
    [
        ("recipient_name", "Mallory Forged"),
        ("recipient_email", "mallory@example.com"),
        ("title", "Doctor of Widgetry"),
        ("issued_at", datetime(2019, 1, 1, tzinfo=timezone.utc)),
        ("metadata_", {"grade": "A+"}),
        ("org_id", uuid.uuid4()),
        ("public_id", "CF-2026-SWAPPED1"),
    ],
)
def test_the_signature_covers_every_field_it_claims_to(db_session, field, value):
    """One case per signed field. A field listed in `covers` but absent from
    the payload would pass this suite silently, which is how the column came
    to cover nothing at all.
    """
    cred = _signed_credential(
        db_session,
        f"CF-2026-CVR{abs(hash(field)) % 10000:04d}X",
        slug=f"covers-{field}",
    )
    assert credential_signature_status(cred) == VALID

    setattr(cred, field, value)
    assert credential_signature_status(cred) == INVALID


def test_the_old_id_only_signature_does_not_pass(db_session):
    """The exact defect, named: a signature over the public_id alone.

    Stamped with the current version so this is not merely the `unverified`
    path — it is a row claiming to be canonically signed while carrying the
    old signature, which is what a downgrade attempt would look like.
    """
    cred = _signed_credential(db_session, "CF-2026-IDONLY01", slug="id-only-org")
    cred.hmac_signature = hmac_sign(cred.public_id)

    assert credential_signature_status(cred) == INVALID


def test_a_signature_from_another_credential_does_not_transfer(db_session):
    """Lifting a valid signature off one row and onto another must fail —
    otherwise one genuine credential authenticates every forgery of it.
    """
    first = _signed_credential(db_session, "CF-2026-DONOR001", slug="donor-org")
    second = _signed_credential(db_session, "CF-2026-RECIP001", slug="recipient-org")

    second.hmac_signature = first.hmac_signature
    assert credential_signature_status(second) == INVALID


def test_field_boundaries_cannot_be_shifted():
    """Two credentials that differ only in where one field ends and the next
    begins must not share a payload.

    A delimiter-joined signing string makes them identical: a recipient named
    `Alice|Advanced` with title `Widgetry` joins to the same bytes as `Alice`
    with title `Advanced|Widgetry`, and one signature covers both.
    """
    common = dict(
        public_id="CF-2026-BOUNDARY",
        org_id="11111111-1111-1111-1111-111111111111",
        recipient_email="a@example.com",
        issued_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )
    left = canonical_payload(recipient_name="Alice|Advanced", title="Widgetry", **common)
    right = canonical_payload(recipient_name="Alice", title="Advanced|Widgetry", **common)

    assert left != right


# ── What must keep working ─────────────────────────────────────────────────


def test_lifecycle_changes_do_not_invalidate_the_signature(db_session):
    """Claiming, revoking and retrying a delivery are the product working.

    The signature attests to what was issued, not to what has happened since,
    so none of these may break it — a scheme that invalidates itself on normal
    use gets switched off.
    """
    cred = _signed_credential(db_session, "CF-2026-LIFECYC1", slug="lifecycle-org")

    cred.status = "claimed"
    cred.claimed_by_user_id = "user_123"
    cred.claimed_at = datetime.now(timezone.utc)
    cred.delivery_status = "sent"
    cred.delivered_at = datetime.now(timezone.utc)
    cred.delivery_attempts = 3
    cred.status = "revoked"
    cred.revoked_at = datetime.now(timezone.utc)
    cred.pdf_url = "https://example.com/x.pdf"

    assert credential_signature_status(cred) == VALID


def test_a_naive_issued_at_signs_the_same_as_an_aware_one():
    """SQLite returns naive datetimes where Postgres returns aware ones.

    Signing `isoformat()` directly would mean a credential signed on one
    backend fails on the other — green in CI, refusing real credentials in
    production.
    """
    aware = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
    naive = aware.replace(tzinfo=None)
    shifted = aware.astimezone(timezone(timedelta(hours=5, minutes=30)))

    common = dict(
        public_id="CF-2026-TIMEZONE",
        org_id="11111111-1111-1111-1111-111111111111",
        recipient_name="Alice",
        recipient_email="a@example.com",
        title="Widgetry",
        metadata={},
    )
    assert canonical_payload(issued_at=aware, **common) == canonical_payload(
        issued_at=naive, **common
    )
    assert canonical_payload(issued_at=aware, **common) == canonical_payload(
        issued_at=shifted, **common
    )


def test_rows_predating_canonical_signing_are_unverified_never_valid(
    client: TestClient, db_session
):
    """Credentials issued before this scheme carry an id-only signature and no
    version. They are real credentials with printed QR codes, so they keep
    resolving — but the API says plainly that nothing was checked, rather than
    reporting them as verified.
    """
    cred = _signed_credential(db_session, "CF-2026-LEGACY01", slug="legacy-sig-org")
    cred.hmac_signature = hmac_sign(cred.public_id)
    cred.signature_version = None
    db_session.commit()

    assert credential_signature_status(cred) == UNVERIFIED

    assert client.get("/verify/CF-2026-LEGACY01").status_code == 200
    assert client.get("/credentials/CF-2026-LEGACY01/badge.json").status_code == 200

    api = client.get("/api/v1/verify/CF-2026-LEGACY01")
    assert api.status_code == 200
    assert api.json()["data"]["signature"]["status"] == UNVERIFIED


def test_an_unknown_signature_version_fails_closed(db_session):
    """A row written by a future build this one cannot check is not a pass."""
    cred = _signed_credential(db_session, "CF-2026-FUTURE01", slug="future-sig-org")
    cred.signature_version = 99

    assert credential_signature_status(cred) == INVALID


def test_an_issued_credential_verifies_end_to_end(client: TestClient, db_session):
    """Through the real issuance service, not a hand-built row: the thing that
    writes the signature and the thing that checks it must agree.
    """
    from api.services.issuance import IssueRequest, issue_credential

    org_id = _org(db_session, "e2e-signing-org")
    db_session.add(
        Template(
            id=uuid.uuid4(),
            org_id=org_id,
            name="Default",
            html_source="<html><body>{{name}}</body></html>",
            is_default=True,
        )
    )
    db_session.commit()

    issued = issue_credential(
        "e2e-signing-org",
        IssueRequest(recipient_name="Alice Example", title="Advanced Widgetry"),
    )

    cred = db_session.query(Credential).filter_by(public_id=issued.public_id).first()
    assert credential_signature_status(cred) == VALID

    api = client.get(f"/api/v1/verify/{issued.public_id}")
    assert api.status_code == 200
    assert api.json()["data"]["signature"]["status"] == VALID


def test_a_bulk_issued_credential_verifies_after_the_worker_runs(
    client: TestClient, db_session
):
    """The join the double-signing exists for.

    Bulk staging signs the pending row, and the worker rewrites `issued_at`
    when the render succeeds. Sign only at staging and every bulk credential
    verifies as tampered the moment it is issued; sign only in the worker and
    the staged row carries a signature over fields it does not have. Neither
    half is visible from the other's tests, which is exactly the failure this
    codebase keeps producing — so this drives both halves and then reads the
    result off the public viewer.
    """
    from unittest.mock import AsyncMock, patch

    from api.core.principal import hash_api_key
    from api.core.worker import _process_batch_sync
    from api.models.api_key import ApiKey
    from api.models.credential import CredentialBatch

    org_id = _org(db_session, "bulk-signing-org")
    raw_key = "cf_live_bulksigning"
    db_session.add(ApiKey(org_id=org_id, key_hash=hash_api_key(raw_key), label="k"))
    template = Template(
        org_id=org_id,
        name="Bulk",
        html_source="<html><body>{{name}} — {{title}}</body></html>",
    )
    db_session.add(template)
    db_session.commit()

    with patch("api.routes.studio.process_batch.defer_async", new=AsyncMock()):
        res = client.post(
            "/api/v1/orgs/bulk-signing-org/credentials/bulk",
            headers={"Authorization": f"Bearer {raw_key}"},
            data={"template_id": str(template.id)},
            files={
                "file": (
                    "people.csv",
                    b"name,title,email\nAda Lovelace,Analytical Engines,\n",
                    "text/csv",
                )
            },
        )
    assert res.status_code == 200, res.text

    batch = db_session.query(CredentialBatch).filter_by(org_id=org_id).first()
    staged = db_session.query(Credential).filter_by(batch_id=batch.id).first()
    # Valid while still pending, too: a row that cannot be verified between
    # staging and rendering is one nothing may safely act on in between.
    assert credential_signature_status(staged) == VALID

    _process_batch_sync(batch.id)
    db_session.expire_all()

    issued = db_session.query(Credential).filter_by(batch_id=batch.id).first()
    assert issued.status == "issued"
    assert credential_signature_status(issued) == VALID
    assert client.get(f"/verify/{issued.public_id}").status_code == 200


def test_the_org_facing_detail_reports_a_mismatch_instead_of_hiding_it(
    client: TestClient, db_session, mock_clerk
):
    """The public routes refuse a tampered credential. The org's own record
    must do the opposite and show it — a 409 here would mean the one person
    who can investigate cannot see which row is affected.
    """
    from api.models.organization import OrgMember

    cred = _signed_credential(db_session, "CF-2026-ORGVIEW1", slug="org-view-org")
    db_session.add(
        OrgMember(
            org_id=cred.org_id, clerk_user_id="test_user_123", role="owner"
        )
    )
    db_session.commit()
    _tamper(db_session, "CF-2026-ORGVIEW1", title="Doctor of Widgetry")

    res = client.get("/api/v1/orgs/org-view-org/credentials/CF-2026-ORGVIEW1")

    assert res.status_code == 200
    body = res.json()["data"]
    assert body["signature"]["status"] == INVALID
    assert body["title"] == "Doctor of Widgetry"
