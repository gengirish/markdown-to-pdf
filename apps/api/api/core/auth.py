"""
Clerk JWT authentication middleware and FastAPI dependencies for CertForge.

Verifies Clerk session tokens (RS256 JWTs) against Clerk's JWKS endpoint.
Extracts user identity and organization context for downstream route handlers.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request

from api.core.config import CLERK_SECRET_KEY

logger = logging.getLogger(__name__)

# Clerk JWKS endpoint for RS256 public key verification
_CLERK_JWKS_URL = "https://api.clerk.com/v1/jwks"
_jwks_cache: Optional[dict] = None


@dataclass
class AuthenticatedUser:
    """Authenticated user context extracted from Clerk JWT."""

    clerk_user_id: str
    clerk_org_id: Optional[str] = None
    clerk_org_role: Optional[str] = None


def _get_jwks() -> dict:
    """Fetch and cache Clerk's JWKS (JSON Web Key Set)."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    try:
        resp = httpx.get(_CLERK_JWKS_URL, headers={
            "Authorization": f"Bearer {CLERK_SECRET_KEY}",
        }, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch Clerk JWKS: {e}")
        raise HTTPException(status_code=503, detail="Authentication service unavailable")


def _verify_clerk_token(token: str) -> dict:
    """Verify a Clerk session JWT and return its claims.

    Uses PyJWT with RS256 verification against Clerk's JWKS.
    Falls back to a simpler approach if PyJWT is not available.
    """
    try:
        import jwt as pyjwt
        from jwt import PyJWKClient
    except ImportError:
        logger.warning("PyJWT not installed — Clerk auth disabled, using dev mode")
        # Dev fallback: trust the token payload without verification
        import base64
        import json
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid token format")
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))

    try:
        jwks_client = PyJWKClient(_CLERK_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk tokens don't always set aud
        )
        return claims
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
    This checks the Clerk JWT claims first (fast path), then falls back
    to a database lookup if needed.
    """
    # Fast path: check JWT claims
    if user.clerk_org_id == org_id and user.clerk_org_role in allowed_roles:
        return

    # Slow path: check database
    from api.models import get_db
    from api.models.organization import OrgMember

    with get_db() as session:
        member = session.query(OrgMember).filter_by(
            org_id=org_id,
            clerk_user_id=user.clerk_user_id,
        ).first()

        if member is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        if member.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
