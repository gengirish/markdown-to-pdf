"""Who is calling: a signed-in human, or a machine holding an API key.

Until now the only answer was "a human with a Clerk session". API keys could be
minted at POST /orgs/{slug}/api-keys and stored hashed, and then *nothing read
them back* — every /api/v1 write route required a browser JWT. A customer could
create a key and find no endpoint that accepted it, which is not an API-first
product however the endpoints are shaped.

A Principal is the one thing route handlers authorise against, whichever way
the caller authenticated:

    user     a Clerk session. Identity only; membership still comes from
             org_members, because a claim only proves whoever minted the token
             said so.
    api_key  a `cf_live_` / `cf_test_` secret. Scoped to exactly one
             organization at mint time, so cross-org access collapses to an
             equality check rather than a database lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

LIVE_PREFIX = "cf_live_"
TEST_PREFIX = "cf_test_"


@dataclass
class Principal:
    """The authenticated caller, normalised across both auth schemes."""

    kind: Literal["user", "api_key"]

    # Set for kind="user".
    clerk_user_id: Optional[str] = None
    email: Optional[str] = None

    # Set for kind="api_key". The organization the key was minted for.
    org_id: Optional[uuid.UUID] = None
    api_key_id: Optional[uuid.UUID] = None

    # Test keys persist to the database but must never send email or bill, so
    # that the API is safe to explore before anyone is ready to spend money.
    is_test: bool = False

    @property
    def is_api_key(self) -> bool:
        return self.kind == "api_key"

    def describe(self) -> str:
        if self.is_api_key:
            return f"api_key {self.api_key_id} (org {self.org_id}{', test' if self.is_test else ''})"
        return f"user {self.clerk_user_id}"


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex of a raw key. Only the hash is ever stored."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def looks_like_api_key(token: str) -> bool:
    return token.startswith((LIVE_PREFIX, TEST_PREFIX))


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")
    return header[7:].strip()


def _principal_from_api_key(raw_key: str) -> Principal:
    from api.models import get_db
    from api.models.api_key import ApiKey

    digest = hash_api_key(raw_key)

    with get_db() as session:
        # Look up by hash, then compare in constant time anyway. The index makes
        # the lookup cheap; compare_digest is what keeps a match from being
        # distinguishable by timing if the column ever stops being unique.
        record = session.query(ApiKey).filter_by(key_hash=digest).first()
        if record is None or not hmac.compare_digest(record.key_hash, digest):
            raise HTTPException(status_code=401, detail="Invalid API key")
        if record.revoked_at is not None:
            raise HTTPException(status_code=401, detail="API key has been revoked")

        principal = Principal(
            kind="api_key",
            org_id=record.org_id,
            api_key_id=record.id,
            is_test=raw_key.startswith(TEST_PREFIX),
        )

        # Best-effort usage stamp. A failure here must never cost the caller
        # their request — the key is already known good at this point.
        try:
            record.last_used_at = datetime.now(timezone.utc)
        except Exception:  # pragma: no cover - defensive
            logger.warning("Could not stamp last_used_at for key %s", record.id)

    return principal


def resolve_principal(request: Request) -> Principal:
    """FastAPI dependency: accept either an API key or a Clerk session token."""
    token = _bearer(request)

    if looks_like_api_key(token):
        return _principal_from_api_key(token)

    from api.core.auth import get_current_user

    user = get_current_user(request)
    return Principal(kind="user", clerk_user_id=user.clerk_user_id, email=user.email)


def require_user(request: Request) -> Principal:
    """For routes that are meaningful only for a human.

    Claiming a credential onto a passport, creating an organization, or minting
    another API key are all acts tied to a person; an API key has no identity to
    attach them to, so it is refused with 403 rather than silently misattributed.
    """
    principal = resolve_principal(request)
    if principal.is_api_key:
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires a signed-in user, not an API key",
        )
    return principal


def require_org_access(
    principal: Principal,
    org_id,
    allowed_roles: tuple[str, ...] = ("owner", "admin", "issuer"),
) -> None:
    """Authorise `principal` against one organization.

    Raises 403 when the caller is not entitled to it. Never trusts a token claim
    for either kind of principal: a user is checked against org_members, and an
    API key can only ever reach the single organization it was minted for.
    """
    try:
        org_uuid = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    if principal.is_api_key:
        if principal.org_id != org_uuid:
            # Deliberately the same message a non-member gets: which
            # organizations exist is not something a key holder should be able
            # to probe for by comparing error text.
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        return

    from api.core.auth import AuthenticatedUser, require_org_role

    require_org_role(
        AuthenticatedUser(clerk_user_id=principal.clerk_user_id, email=principal.email),
        org_uuid,
        allowed_roles=allowed_roles,
    )
