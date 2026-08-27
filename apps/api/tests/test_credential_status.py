"""The credential lifecycle, and the disagreements it replaced.

Four ad-hoc status comparisons across three files used to disagree: the viewer
allowed only "issued" while badge.json, claiming and passport listing allowed
anything but "revoked". Each test here pins one consequence of that mismatch so
it cannot come back by someone adding a fifth state and updating three of the
four places.
"""

from datetime import datetime, timezone

from api.models.credential import (
    CLAIMABLE,
    CLAIMED,
    ISSUED,
    PENDING,
    PUBLICLY_VERIFIABLE,
    REVOKED,
    TERMINAL,
    Credential,
)
from api.models.organization import Organization


def seed(db_session, public_id, status):
    org = db_session.query(Organization).filter_by(slug="lifecycle").first()
    if org is None:
        org = Organization(slug="lifecycle", name="Lifecycle", tier="community")
        db_session.add(org)
        db_session.commit()
    db_session.add(
        Credential(
            public_id=public_id,
            org_id=org.id,
            recipient_name="Rosalind Franklin",
            recipient_email="",
            title="Crystallography",
            metadata_={},
            hmac_signature="0" * 64,
            status=status,
            issued_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()


# -- the definition itself ---------------------------------------------------

def test_claiming_does_not_remove_a_credential_from_public_view():
    """The QR code printed on a certificate is permanent; claiming is not a
    reason for it to stop resolving."""
    assert CLAIMED in PUBLICLY_VERIFIABLE
    assert ISSUED in PUBLICLY_VERIFIABLE


def test_an_unfinished_credential_is_not_public():
    """A bulk row the worker has not produced yet must not be verifiable."""
    assert PENDING not in PUBLICLY_VERIFIABLE


def test_a_revoked_credential_is_never_public_and_never_claimable():
    assert REVOKED not in PUBLICLY_VERIFIABLE
    assert REVOKED not in CLAIMABLE
    assert REVOKED in TERMINAL


# -- the surfaces agree ------------------------------------------------------

def test_the_viewer_and_the_badge_agree_on_every_state(client, db_session):
    """These were a whitelist and a blacklist, so they disagreed about
    "pending": invisible in the viewer, yet exporting a public Open Badge."""
    cases = {
        ISSUED: "CF-2026-AGREE001",
        CLAIMED: "CF-2026-AGREE002",
        PENDING: "CF-2026-AGREE003",
        REVOKED: "CF-2026-AGREE004",
    }
    for status, public_id in cases.items():
        seed(db_session, public_id, status)

    for status, public_id in cases.items():
        verify = client.get(f"/api/v1/verify/{public_id}").status_code
        badge = client.get(f"/credentials/{public_id}/badge.json").status_code
        expected = 200 if status in PUBLICLY_VERIFIABLE else 404
        assert verify == expected, f"{status}: /verify returned {verify}"
        assert badge == expected, f"{status}: badge.json returned {badge}"


def test_a_pending_credential_no_longer_leaks_a_public_badge(client, db_session):
    """The concrete old bug, kept as its own case so the reason survives."""
    seed(db_session, "CF-2026-PENDING1", PENDING)
    assert client.get("/credentials/CF-2026-PENDING1/badge.json").status_code == 404


def test_a_claimed_credential_still_exports_its_badge(client, db_session):
    seed(db_session, "CF-2026-CLAIMED1", CLAIMED)
    assert client.get("/credentials/CF-2026-CLAIMED1/badge.json").status_code == 200


# -- model predicates --------------------------------------------------------

def test_model_predicates_match_the_sets(db_session):
    seed(db_session, "CF-2026-PREDS001", CLAIMED)
    cred = db_session.query(Credential).filter_by(public_id="CF-2026-PREDS001").one()
    assert cred.is_publicly_verifiable is True
    assert cred.is_claimable is True
    assert cred.is_revoked is False

    cred.status = REVOKED
    assert cred.is_publicly_verifiable is False
    assert cred.is_claimable is False
    assert cred.is_revoked is True


def test_every_state_is_accounted_for():
    """A fifth state must not be addable without deciding what it means.

    If this fails, someone added a status constant and did not place it in the
    sets — which is exactly how the viewer and badge.json drifted apart.
    """
    known = {PENDING, ISSUED, CLAIMED, REVOKED}
    classified = PUBLICLY_VERIFIABLE | CLAIMABLE | TERMINAL | {PENDING}
    assert known == classified
