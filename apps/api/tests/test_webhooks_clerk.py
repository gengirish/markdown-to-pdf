"""Clerk webhook receiver: signature verification and database sync.

Signature verification is implemented in-repo rather than via the `svix`
package, so the adversarial cases are covered here explicitly: forged bodies,
wrong keys, replays, and secret rotation.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

from api.models.organization import Organization, OrgMember
from api.routes import webhooks_clerk as wh

SECRET = "whsec_" + base64.b64encode(b"a-test-signing-key-for-clerk").decode()
OTHER_SECRET = "whsec_" + base64.b64encode(b"a-completely-different-key!!").decode()


def sign(body, secret=SECRET, msg_id="msg_1", ts=None):
    ts = ts if ts is not None else int(time.time())
    key = base64.b64decode(secret.split("_", 1)[1])
    signed = f"{msg_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}"}


def post(client, payload, secret=SECRET, headers=None, ts=None, body=None):
    raw = body if body is not None else json.dumps(payload).encode()
    h = sign(raw, secret, ts=ts) if headers is None else headers
    return client.post(
        "/api/v1/webhooks/clerk",
        content=raw,
        headers={**h, "content-type": "application/json"},
    )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(wh, "CLERK_WEBHOOK_SECRET", SECRET)


def org_created(clerk_id="org_test1", slug="acme", name="Acme"):
    return {
        "type": "organization.created",
        "data": {"id": clerk_id, "slug": slug, "name": name},
    }


def membership(event, clerk_id="org_test1", user="user_1", role="org:admin", slug="acme"):
    return {
        "type": event,
        "data": {
            "organization": {"id": clerk_id, "slug": slug, "name": "Acme"},
            "public_user_data": {"user_id": user},
            "role": role,
        },
    }


# -- failing closed ---------------------------------------------------------

def test_unconfigured_secret_rejects_every_request(client, monkeypatch):
    """An unset secret must refuse, not accept: this endpoint grants membership."""
    monkeypatch.setattr(wh, "CLERK_WEBHOOK_SECRET", "")
    assert post(client, org_created()).status_code == 503


def test_missing_signature_headers_are_rejected(client, configured):
    assert post(client, org_created(), headers={}).status_code == 401


# -- signature verification -------------------------------------------------

def test_valid_signature_is_accepted(client, configured):
    assert post(client, org_created()).status_code == 200


def test_body_tampered_after_signing_is_rejected(client, configured):
    original = json.dumps(org_created()).encode()
    headers = sign(original)
    forged = json.dumps(org_created(name="Attacker Inc")).encode()
    assert post(client, {}, headers=headers, body=forged).status_code == 401


def test_signature_from_a_different_secret_is_rejected(client, configured):
    assert post(client, org_created(), secret=OTHER_SECRET).status_code == 401


def test_replayed_old_timestamp_is_rejected(client, configured):
    assert post(client, org_created(), ts=int(time.time()) - 3600).status_code == 401


def test_timestamp_far_in_the_future_is_rejected(client, configured):
    assert post(client, org_created(), ts=int(time.time()) + 3600).status_code == 401


def test_rotation_accepts_either_signature_in_the_header(client, configured):
    """During rotation Svix sends several v1 signatures; matching one suffices."""
    raw = json.dumps(org_created(clerk_id="org_rot", slug="rot")).encode()
    headers = sign(raw)
    stale = "v1,YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwPT0="
    headers["svix-signature"] = stale + " " + headers["svix-signature"]
    assert post(client, {}, headers=headers, body=raw).status_code == 200


def test_signature_verification_is_pure_and_offline(configured):
    raw = b'{"hello": "world"}'
    assert wh.verify_signature(SECRET, sign(raw), raw) is True
    assert wh.verify_signature(OTHER_SECRET, sign(raw), raw) is False


# -- database sync ----------------------------------------------------------

def test_organization_created_persists_the_clerk_id(client, configured, db_session):
    post(client, org_created(clerk_id="org_aaa", slug="aaa", name="Triple A"))
    org = db_session.query(Organization).filter_by(clerk_org_id="org_aaa").one()
    assert org.slug == "aaa"
    assert org.name == "Triple A"
    assert org.tier == "community"


def test_organization_updated_renames_without_duplicating(client, configured, db_session):
    post(client, org_created(clerk_id="org_bbb", slug="bbb", name="Before"))
    post(
        client,
        {
            "type": "organization.updated",
            "data": {"id": "org_bbb", "slug": "bbb-renamed", "name": "After"},
        },
    )
    rows = db_session.query(Organization).filter_by(clerk_org_id="org_bbb").all()
    assert len(rows) == 1
    assert rows[0].slug == "bbb-renamed"
    assert rows[0].name == "After"


def test_replaying_the_same_event_is_idempotent(client, configured, db_session):
    for _ in range(3):
        post(client, org_created(clerk_id="org_idem", slug="idem"))
    assert db_session.query(Organization).filter_by(clerk_org_id="org_idem").count() == 1


def test_organization_deleted_does_not_destroy_issued_credentials(client, configured, db_session):
    """Organization.credentials cascades delete-orphan, so the row must survive.

    Issued credentials are permanent public records with QR codes printed on
    paper. Deleting an org in Clerk must never be able to invalidate them.
    """
    post(client, org_created(clerk_id="org_del", slug="del"))
    r = post(client, {"type": "organization.deleted", "data": {"id": "org_del"}})
    assert r.status_code == 200
    assert db_session.query(Organization).filter_by(clerk_org_id="org_del").count() == 1


def test_first_member_becomes_the_owner(client, configured, db_session):
    post(
        client,
        membership("organizationMembership.created", clerk_id="org_own", slug="own", user="user_first"),
    )
    org = db_session.query(Organization).filter_by(clerk_org_id="org_own").one()
    member = (
        db_session.query(OrgMember)
        .filter_by(org_id=org.id, clerk_user_id="user_first")
        .one()
    )
    assert member.role == "owner"


def test_later_members_map_to_their_clerk_role(client, configured, db_session):
    post(client, membership("organizationMembership.created", clerk_id="org_two", slug="two", user="user_a"))
    post(
        client,
        membership(
            "organizationMembership.created",
            clerk_id="org_two",
            slug="two",
            user="user_b",
            role="org:member",
        ),
    )
    org = db_session.query(Organization).filter_by(clerk_org_id="org_two").one()
    roles = {
        m.clerk_user_id: m.role
        for m in db_session.query(OrgMember).filter_by(org_id=org.id)
    }
    assert roles == {"user_a": "owner", "user_b": "issuer"}


def test_membership_deleted_removes_a_non_owner(client, configured, db_session):
    post(client, membership("organizationMembership.created", clerk_id="org_rm", slug="rm", user="user_owner"))
    post(
        client,
        membership(
            "organizationMembership.created",
            clerk_id="org_rm",
            slug="rm",
            user="user_gone",
            role="org:member",
        ),
    )
    post(client, membership("organizationMembership.deleted", clerk_id="org_rm", slug="rm", user="user_gone"))
    org = db_session.query(Organization).filter_by(clerk_org_id="org_rm").one()
    left = {m.clerk_user_id for m in db_session.query(OrgMember).filter_by(org_id=org.id)}
    assert left == {"user_owner"}


def test_the_owner_cannot_be_removed_by_webhook(client, configured, db_session):
    """An org with no owner cannot be administered, so refuse the removal."""
    post(client, membership("organizationMembership.created", clerk_id="org_keep", slug="keep", user="user_boss"))
    post(client, membership("organizationMembership.deleted", clerk_id="org_keep", slug="keep", user="user_boss"))
    org = db_session.query(Organization).filter_by(clerk_org_id="org_keep").one()
    assert db_session.query(OrgMember).filter_by(org_id=org.id).count() == 1


def test_a_preexisting_org_is_adopted_by_slug_rather_than_duplicated(client, configured, db_session):
    """Orgs created before Clerk sync have clerk_org_id NULL; link, do not clone."""
    db_session.add(Organization(slug="legacy", name="Legacy", tier="community"))
    db_session.commit()
    post(client, org_created(clerk_id="org_legacy", slug="legacy", name="Legacy"))
    rows = db_session.query(Organization).filter_by(slug="legacy").all()
    assert len(rows) == 1
    assert rows[0].clerk_org_id == "org_legacy"


def test_unhandled_events_are_acknowledged_not_errors(client, configured):
    r = post(client, {"type": "user.created", "data": {"id": "user_x"}})
    assert r.status_code == 200
    assert "not handled" in r.json()["data"]["result"]
