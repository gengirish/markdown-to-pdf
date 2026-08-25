"""Clerk webhook receiver.

Clerk is the source of truth for organizations and membership; this is how that
truth reaches the CertForge database. Without it a user can sign in, create an
organization in Clerk, and find nothing to work with — every /api/v1 route is
org-scoped and authorises against `org_members`, which only this handler fills.

Signature verification implements the Standard Webhooks / Svix scheme directly
rather than pulling in the `svix` package: the algorithm is short and fully
specified, the image stays lean, and it can be tested offline with no network.
The trade-off is that correctness here is on us, so `tests/test_webhooks_clerk.py`
covers replay, tampering, rotation and tolerance explicitly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from api.core.config import CLERK_WEBHOOK_SECRET
from api.core.envelope import ApiResponse
from api.models import get_db
from api.models.organization import Organization, OrgMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Svix rejects timestamps outside five minutes in either direction. The past
# bound blocks replay of a captured request; the future bound blocks a forged
# timestamp buying an attacker an indefinite window.
_TOLERANCE_SECONDS = 5 * 60

# Clerk roles are "org:admin" / "org:member"; CertForge stores owner/admin/issuer.
_ROLE_MAP = {
    "org:admin": "admin",
    "admin": "admin",
    "org:member": "issuer",
    "basic_member": "issuer",
    "member": "issuer",
}


def _signing_key(secret: str) -> bytes:
    """Svix secrets are `whsec_<base64>`; the bytes after the prefix are the key."""
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    return base64.b64decode(raw)


def verify_signature(secret: str, headers, body: bytes, *, now: float | None = None) -> bool:
    """Return True when `body` carries a valid Svix signature for `secret`."""
    svix_id = headers.get("svix-id") or ""
    svix_ts = headers.get("svix-timestamp") or ""
    svix_sig = headers.get("svix-signature") or ""
    if not (svix_id and svix_ts and svix_sig):
        return False

    try:
        sent_at = int(svix_ts)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - sent_at) > _TOLERANCE_SECONDS:
        return False

    try:
        key = _signing_key(secret)
    except Exception:
        logger.error("CLERK_WEBHOOK_SECRET is not a valid whsec_ value")
        return False

    signed = f"{svix_id}.{svix_ts}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # The header carries space-separated `v1,<sig>` entries so a secret can be
    # rotated without downtime — both the old and new signature arrive together,
    # and matching any one of them is enough.
    for part in svix_sig.split():
        version, _, candidate = part.partition(",")
        if version == "v1" and hmac.compare_digest(candidate, expected):
            return True
    return False


def _role_for(clerk_role: str | None) -> str:
    return _ROLE_MAP.get((clerk_role or "").lower(), "issuer")


def _upsert_org(session, data: dict) -> Organization | None:
    clerk_org_id = data.get("id")
    if not clerk_org_id:
        return None

    org = session.query(Organization).filter_by(clerk_org_id=clerk_org_id).first()
    if org is None:
        # An org may already exist from before Clerk sync — adopt it by slug
        # rather than colliding with the unique slug constraint.
        org = session.query(Organization).filter_by(slug=data.get("slug")).first()
        if org is not None and org.clerk_org_id is None:
            org.clerk_org_id = clerk_org_id
        elif org is None:
            org = Organization(
                clerk_org_id=clerk_org_id,
                slug=data.get("slug") or clerk_org_id,
                name=data.get("name") or "Untitled organization",
                logo_url=data.get("image_url"),
                tier="community",
            )
            session.add(org)
            session.flush()

    if data.get("name"):
        org.name = data["name"]
    if data.get("slug"):
        org.slug = data["slug"]
    if data.get("image_url"):
        org.logo_url = data["image_url"]
    return org


def _handle(event: str, data: dict) -> str:
    """Apply one Clerk event. Returns a short description of what was done."""
    with get_db() as session:
        if event in ("organization.created", "organization.updated"):
            org = _upsert_org(session, data)
            return f"synced organization {org.slug}" if org else "ignored: no organization id"

        if event == "organization.deleted":
            # Deliberately NOT deleting. Organization.credentials cascades with
            # delete-orphan, so removing the row would destroy every credential
            # that org ever issued — and issued credentials are permanent public
            # records with QR codes printed on paper. Deleting an org in Clerk
            # must never be able to invalidate them.
            logger.warning(
                "Clerk organization.deleted for %s — row retained on purpose "
                "(deleting it would cascade to issued credentials)",
                data.get("id"),
            )
            return "acknowledged, row retained"

        if event in ("organizationMembership.created", "organizationMembership.updated"):
            org_data = data.get("organization") or {}
            user_data = (data.get("public_user_data") or {})
            clerk_user_id = user_data.get("user_id") or data.get("user_id")
            org = _upsert_org(session, org_data)
            if not (org and clerk_user_id):
                return "ignored: incomplete membership payload"

            role = _role_for(data.get("role"))
            member = (
                session.query(OrgMember)
                .filter_by(org_id=org.id, clerk_user_id=clerk_user_id)
                .first()
            )
            if member is None:
                # The first member to arrive owns the org: Clerk reports the
                # creator as org:admin, and CertForge needs exactly one owner.
                is_first = not session.query(OrgMember).filter_by(org_id=org.id).first()
                session.add(
                    OrgMember(
                        org_id=org.id,
                        clerk_user_id=clerk_user_id,
                        role="owner" if is_first else role,
                    )
                )
                return f"added {clerk_user_id} to {org.slug}"
            # Never demote the owner off the back of a Clerk role change; an org
            # with no owner cannot be administered.
            if member.role != "owner":
                member.role = role
            return f"updated {clerk_user_id} in {org.slug}"

        if event == "organizationMembership.deleted":
            org_data = data.get("organization") or {}
            clerk_user_id = (data.get("public_user_data") or {}).get("user_id") or data.get("user_id")
            org = session.query(Organization).filter_by(clerk_org_id=org_data.get("id")).first()
            if not (org and clerk_user_id):
                return "ignored: unknown organization or user"
            member = (
                session.query(OrgMember)
                .filter_by(org_id=org.id, clerk_user_id=clerk_user_id)
                .first()
            )
            if member is None:
                return "ignored: not a member"
            if member.role == "owner":
                logger.warning(
                    "Refusing to remove the owner of %s via webhook", org.slug
                )
                return "refused: cannot remove the owner"
            session.delete(member)
            return f"removed {clerk_user_id} from {org.slug}"

    return f"ignored: {event} is not handled"


@router.post("/clerk", response_model=ApiResponse[dict])
async def clerk_webhook(request: Request):
    """Receive a Clerk (Svix) webhook and mirror it into the database."""
    # Fail closed when unconfigured. This endpoint grants organization
    # membership, so an unset secret must reject rather than accept anything.
    if not CLERK_WEBHOOK_SECRET:
        logger.error("Clerk webhook received but CLERK_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook signing is not configured")

    body = await request.body()
    if not verify_signature(CLERK_WEBHOOK_SECRET, request.headers, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")

    event = payload.get("type") or ""
    data = payload.get("data") or {}
    result = _handle(event, data)
    logger.info("Clerk webhook %s: %s", event, result)
    return ApiResponse.ok({"event": event, "result": result})
