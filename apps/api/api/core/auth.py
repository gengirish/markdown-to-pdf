"""
Clerk JWT authentication middleware and FastAPI dependencies for CertForge.

Verifies Clerk session tokens (RS256 JWTs) against Clerk's JWKS endpoint.
Extracts user identity and organization context for downstream route handlers.

Security note: this module fails *closed*. If PyJWT is missing or the JWKS
endpoint cannot be resolved, requests are rejected with 503 rather than falling
back to reading unverified claims out of the token body — a fallback that would
let anyone mint a token granting themselves any identity or org role.
"""

import base64
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from api.core.config import CLERK_JWKS_URL, CLERK_PUBLISHABLE_KEY

logger = logging.getLogger(__name__)

_jwks_client = None


@dataclass
class AuthenticatedUser:
    """Authenticated user context extracted from Clerk JWT."""

    clerk_user_id: str
    clerk_org_id: Optional[str] = None
    clerk_org_role: Optional[str] = None


def _jwks_url_from_publishable_key(publishable_key: str) -> str:
    """Derive the Clerk Frontend API JWKS URL from a publishable key.

    Clerk publishable keys are `pk_test_<base64url(frontend-api-host + "$")>`,
    and every instance serves its signing keys at
    `https://<frontend-api-host>/.well-known/jwks.json`. Deriving it means a
    deployment only needs the key it already sets for the frontend.
    """
    key = (publishable_key or "").strip()
    for prefix in ("pk_test_", "pk_live_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    else:
        return ""
    try:
        decoded = base64.b64decode(key + "=" * (-len(key) % 4)).decode("utf-8")
    except Exception:
        return ""
    host = decoded.rstrip("$").strip()
    if not host:
        return ""
    return f"https://{host}/.well-known/jwks.json"


def _resolve_jwks_url() -> str:
    """Return the JWKS URL to verify against, or "" if Clerk is unconfigured."""
    if CLERK_JWKS_URL:
        return CLERK_JWKS_URL
    return _jwks_url_from_publishable_key(CLERK_PUBLISHABLE_KEY)


def _require_pyjwt():
    """Return the PyJWT module, or raise 503 if it is not installed.

    Never degrade to trusting unverified tokens — see the module docstring.
    PyJWT[crypto] is pinned in requirements.txt precisely so this cannot happen
    silently in a deployed environment.
    """
    try:
        import jwt as pyjwt
    except ImportError:
        logger.error("PyJWT is not installed; Clerk authentication cannot verify tokens")
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    return pyjwt


def _get_jwks_client():
    """Get or create the cached PyJWKClient. Raises 503 if auth is unusable."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client

    PyJWKClient = _require_pyjwt().PyJWKClient

    jwks_url = _resolve_jwks_url()
    if not jwks_url:
        logger.error(
            "Clerk JWKS URL is not configured — set CLERK_JWKS_URL or "
            "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
        )
        raise HTTPException(status_code=503, detail="Authentication service unavailable")

    # cache_jwk_set keeps the signing keys in memory for `lifespan` seconds so
    # verification does not hit Clerk on every request.
    _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=10)
    return _jwks_client


def _verify_clerk_token(token: str) -> dict:
    """Verify a Clerk session JWT (RS256, against Clerk's JWKS) and return its claims."""
    pyjwt = _require_pyjwt()
    jwks_client = _get_jwks_client()
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except pyjwt.PyJWKClientError as e:
        logger.warning(f"Could not resolve Clerk signing key: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    except Exception as e:
        logger.error(f"Failed to fetch Clerk JWKS: {e}")
        raise HTTPException(status_code=503, detail="Authentication service unavailable")

    try:
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["exp", "sub"],
                "verify_aud": False,  # Clerk tokens don't always set aud
            },
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except pyjwt.InvalidTokenError as e:
        logger.warning(f"Invalid Clerk token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")


def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency: extract and verify the authenticated user from Clerk JWT.

    Usage:
        @app.get("/api/v1/protected")
        async def protected(user: AuthenticatedUser = Depends(get_current_user)):
            ...
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = auth_header[7:]
    claims = _verify_clerk_token(token)

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    return AuthenticatedUser(
        clerk_user_id=user_id,
        clerk_org_id=claims.get("org_id"),
        clerk_org_role=claims.get("org_role"),
    )


def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """FastAPI dependency: extract user if auth header present, None otherwise.

    Use for endpoints that behave differently for authenticated vs anonymous users.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def require_org_role(
    user: AuthenticatedUser,
    org_id: str,
    allowed_roles: tuple[str, ...] = ("owner", "admin", "issuer"),
) -> None:
    """Verify the user has one of the allowed roles in the specified org.

    Raises 403 if the user is not a member or lacks the required role.

    Membership is always resolved against the `org_members` table. There used to
    be a "fast path" that accepted `user.clerk_org_id == org_id` straight from
    the JWT claims, but callers pass CertForge's own organization UUID while the
    claim carries a Clerk org id (`org_...`) — the two are different namespaces,
    so the comparison could only ever match a token that had been crafted to
    make it match.
    """
    import uuid as _uuid

    from api.models import get_db
    from api.models.organization import OrgMember

    # Callers pass str(org.id); the column is UUID(as_uuid=True), whose bind
    # processor expects a UUID instance and raises on a plain string.
    try:
        org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    with get_db() as session:
        member = session.query(OrgMember).filter_by(
            org_id=org_uuid,
            clerk_user_id=user.clerk_user_id,
        ).first()

        if member is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        if member.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
