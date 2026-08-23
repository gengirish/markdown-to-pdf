"""Regressions for credential claiming and public passports.

The claim path had never run: it read `user.email` off an AuthenticatedUser that
had no such field, so the first person ever to claim a credential would have hit
an AttributeError. Both routes also answered their error cases with HTTP 200 and
an error body, telling the caller the request had succeeded.
"""

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.core import auth
from api.core.auth import AuthenticatedUser, get_current_user
from api.index import app
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.passport import Passport


@contextlib.contextmanager
def auth_as(clerk_user_id: str, email=None):
    """Authenticate the next requests as this Clerk user.

    Separate from conftest's `mock_clerk` because these tests need to switch
    identities mid-test — and to vary whether the token carried an email.
    """
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        clerk_user_id=clerk_user_id, email=email
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _issue_credential(db_session: Session, public_id: str, **overrides) -> Credential:
    """Put an issued credential in the database for someone to claim."""
    org = Organization(id=uuid.uuid4(), name="Passport Test Org", slug=f"pp-{public_id}")
    db_session.add(org)
    cred = Credential(
        id=uuid.uuid4(),
        public_id=public_id,
        org_id=org.id,
        recipient_name="Priya Sharma",
        recipient_email="priya@example.edu",
        title="Advanced Python",
        metadata_={"course": "Advanced Python", "hours": "40"},
        hmac_signature="0" * 64,
        **overrides,
    )
    db_session.add(cred)
    db_session.commit()
    return cred


# ── The email claim ───────────────────────────────────────────────────────

def test_authenticated_user_without_an_email_claim_does_not_crash_the_claim(
    client: TestClient, db_session
):
    """Clerk's stock session token has no email claim; claiming must still work.

    `passports.claim_credential` read `user.email` unconditionally, and
    AuthenticatedUser had no such attribute — the very first claim raised
    AttributeError and returned 500.
    """
    _issue_credential(db_session, "CF-NOEMAIL-1")

    with auth_as("user_2NoEmailAtAll"):
        res = client.post("/api/v1/claims/CF-NOEMAIL-1")

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    # Falls back to the Clerk id with its meaningless "user_" prefix stripped.
    assert body["data"]["username"].startswith("2noemailatall-")


def test_email_claim_becomes_the_username_when_the_jwt_template_supplies_one(
    client: TestClient, db_session
):
    _issue_credential(db_session, "CF-EMAIL-1")

    with auth_as("user_2WithEmail", email="Priya.Sharma@example.edu"):
        res = client.post("/api/v1/claims/CF-EMAIL-1")

    assert res.status_code == 200
    assert res.json()["data"]["username"].startswith("priya-sharma-")


def test_email_is_read_from_whichever_claim_the_clerk_template_used():
    """Clerk instances spell the custom email claim several ways."""
    assert auth._email_from_claims({"email": "a@b.com"}) == "a@b.com"
    assert auth._email_from_claims({"primary_email_address": "c@d.com"}) == "c@d.com"
    assert auth._email_from_claims({"user_email": "e@f.com"}) == "e@f.com"


@pytest.mark.parametrize("claims", [{}, {"email": ""}, {"email": None}, {"email": 42}])
def test_absent_or_malformed_email_claim_yields_none_rather_than_raising(claims):
    assert auth._email_from_claims(claims) is None


# ── Claiming ──────────────────────────────────────────────────────────────

def test_claiming_creates_a_passport_and_links_the_credential(
    client: TestClient, db_session
):
    _issue_credential(db_session, "CF-LINK-1")

    with auth_as("user_2Linker", email="linker@example.edu"):
        res = client.post("/api/v1/claims/CF-LINK-1")
    username = res.json()["data"]["username"]

    profile = client.get(f"/api/v1/passports/{username}")
    assert profile.status_code == 200
    creds = profile.json()["data"]["credentials"]
    assert [c["id"] for c in creds] == ["CF-LINK-1"]

    db_session.expire_all()
    cred = db_session.query(Credential).filter_by(public_id="CF-LINK-1").one()
    assert cred.claimed_by_user_id == "user_2Linker"
    assert cred.claimed_at is not None


def test_claiming_leaves_the_credential_verifiable(client: TestClient, db_session):
    """`status` must stay "issued": /verify treats anything else as nonexistent,
    and the QR code printed on the certificate resolves through it."""
    _issue_credential(db_session, "CF-STATUS-1")

    with auth_as("user_2Status"):
        assert client.post("/api/v1/claims/CF-STATUS-1").status_code == 200

    db_session.expire_all()
    assert db_session.query(Credential).filter_by(public_id="CF-STATUS-1").one().status == "issued"


def test_repeat_claim_by_the_same_user_is_idempotent(client: TestClient, db_session):
    """A second POST must reuse the passport and not duplicate the link."""
    _issue_credential(db_session, "CF-IDEM-1")

    with auth_as("user_2Repeat", email="repeat@example.edu"):
        first = client.post("/api/v1/claims/CF-IDEM-1")
        second = client.post("/api/v1/claims/CF-IDEM-1")

    assert first.status_code == second.status_code == 200
    username = first.json()["data"]["username"]
    assert second.json()["data"]["username"] == username

    assert db_session.query(Passport).filter_by(clerk_user_id="user_2Repeat").count() == 1
    creds = client.get(f"/api/v1/passports/{username}").json()["data"]["credentials"]
    assert len(creds) == 1


def test_second_user_claiming_an_owned_credential_gets_403_not_200(
    client: TestClient, db_session
):
    """The "already claimed" branch used to return HTTP 200 with an error body."""
    _issue_credential(db_session, "CF-STEAL-1")

    with auth_as("user_2Owner"):
        assert client.post("/api/v1/claims/CF-STEAL-1").status_code == 200

    with auth_as("user_2Thief"):
        res = client.post("/api/v1/claims/CF-STEAL-1")

    assert res.status_code == 403
    assert res.json()["error"]["code"] == 403

    db_session.expire_all()
    cred = db_session.query(Credential).filter_by(public_id="CF-STEAL-1").one()
    assert cred.claimed_by_user_id == "user_2Owner"


def test_claiming_an_unknown_credential_returns_404_not_200(client: TestClient):
    with auth_as("user_2Nobody"):
        res = client.post("/api/v1/claims/CF-DOES-NOT-EXIST")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == 404


def test_revoked_credential_cannot_be_claimed(client: TestClient, db_session):
    """/verify already treats a revoked credential as nonexistent."""
    _issue_credential(db_session, "CF-REVOKED-1", status="revoked")

    with auth_as("user_2Revoked"):
        res = client.post("/api/v1/claims/CF-REVOKED-1")

    assert res.status_code == 404


# ── Public passport ───────────────────────────────────────────────────────

def test_unknown_passport_returns_404_not_200(client: TestClient):
    res = client.get("/api/v1/passports/nobody-here")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == 404


def test_private_passport_returns_403_not_200(client: TestClient, db_session):
    db_session.add(
        Passport(
            id=uuid.uuid4(),
            clerk_user_id="user_2Private",
            username="private-profile",
            display_name="Private",
            is_public=False,
        )
    )
    db_session.commit()

    res = client.get("/api/v1/passports/private-profile")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == 403


def test_passport_returns_the_credentials_stored_metadata(client: TestClient, db_session):
    """`cred.metadata` on a declarative model is SQLAlchemy's MetaData object,
    not the JSON column — serialising it blew up the whole response."""
    _issue_credential(db_session, "CF-META-1")

    with auth_as("user_2Meta"):
        username = client.post("/api/v1/claims/CF-META-1").json()["data"]["username"]

    res = client.get(f"/api/v1/passports/{username}")
    assert res.status_code == 200
    assert res.json()["data"]["credentials"][0]["metadata"] == {
        "course": "Advanced Python",
        "hours": "40",
    }
