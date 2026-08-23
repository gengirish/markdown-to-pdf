"""Passport (public credential profile) and credential-claim endpoints."""

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.models import get_db
from api.models.credential import Credential
from api.models.passport import Passport, PassportCredential
from api.core.envelope import ApiResponse
from api.core.auth import get_current_user, AuthenticatedUser

router = APIRouter(prefix="/passports", tags=["passports"])
claims_router = APIRouter(prefix="/claims", tags=["claims"])

_USERNAME_FALLBACK = "member"


def _slugify(value: str) -> str:
    """Reduce arbitrary text to the [a-z0-9-] a username may contain."""
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:40]


def _passport_identity(user: AuthenticatedUser) -> tuple[str, str]:
    """Return (username, display_name) for someone claiming their first credential.

    The local part of the email reads best, but Clerk only sends an email when
    the instance's JWT template asks for one (see core/auth.py), so the Clerk
    user id has to carry the fallback: a passport must be creatable for a user
    whose token is the stock Clerk session token.

    The random suffix is what makes the username unique. Two people called
    "priya" may claim on the same day, and neither picked the name, so neither
    has a prior claim to the bare one.
    """
    email = user.email or ""
    local = email.split("@", 1)[0] if "@" in email else ""
    seed = _slugify(local)
    display_name = local.strip()
    if not seed:
        # Clerk ids look like "user_2abcDEF..."; the prefix carries no meaning.
        seed = _slugify(re.sub(r"^user_", "", user.clerk_user_id)) or _USERNAME_FALLBACK
        display_name = seed
    return f"{seed}-{uuid.uuid4().hex[:8]}", display_name


@claims_router.post("/{credential_id}", response_model=ApiResponse[dict])
def claim_credential(
    credential_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Claim a credential using its public ID.

    Idempotent: re-claiming a credential you already hold returns the same
    passport rather than creating a second one or a duplicate link.
    """
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=credential_id).first()
        # Revoked counts as absent here, as it does in /verify — claiming one
        # would only pin a withdrawn credential to a public profile.
        if not cred or cred.status == "revoked":
            raise HTTPException(status_code=404, detail="Credential not found")

        if cred.claimed_by_user_id and cred.claimed_by_user_id != user.clerk_user_id:
            raise HTTPException(
                status_code=403, detail="Credential already claimed by another user"
            )

        # Ensure passport exists
        passport = session.query(Passport).filter_by(clerk_user_id=user.clerk_user_id).first()
        if not passport:
            username, display_name = _passport_identity(user)
            passport = Passport(
                clerk_user_id=user.clerk_user_id,
                username=username,
                display_name=display_name,
                bio="",
                is_public=True
            )
            session.add(passport)
            session.flush()

        # Link credential
        existing_link = session.query(PassportCredential).filter_by(
            passport_id=passport.id,
            credential_id=cred.id
        ).first()

        if not existing_link:
            link = PassportCredential(
                passport_id=passport.id,
                credential_id=cred.id,
                display_order=0,
                pinned=False
            )
            session.add(link)

        # Claiming records who holds the credential and deliberately leaves
        # `status` at "issued": verify.py treats any other value as
        # unverifiable, and the QR printed on the certificate must keep
        # resolving after the recipient claims it.
        cred.claimed_by_user_id = user.clerk_user_id
        if cred.claimed_at is None:
            cred.claimed_at = datetime.now(timezone.utc)

        # Read the response values out before committing — commit expires the
        # instances, and re-reading them would cost two extra SELECTs.
        result = {"username": passport.username, "credential_id": cred.public_id}
        session.commit()

        return ApiResponse.ok(result)

@router.get("/{username}", response_model=ApiResponse[dict])
def get_passport(username: str):
    """Fetch public passport profile and its credentials."""
    with get_db() as session:
        passport = session.query(Passport).filter_by(username=username).first()
        if not passport:
            raise HTTPException(status_code=404, detail="Passport not found")

        if not passport.is_public:
            raise HTTPException(status_code=403, detail="Passport is private")

        links = session.query(PassportCredential).filter_by(passport_id=passport.id).all()

        creds = []
        for link in links:
            # Re-fetch credential to get full details
            cred = session.query(Credential).filter_by(id=link.credential_id).first()
            if cred and cred.status != "revoked":
                creds.append({
                    "id": cred.public_id,
                    "title": cred.title,
                    "recipient_name": cred.recipient_name,
                    "issued_at": cred.issued_at.isoformat(),
                    # `.metadata_`, not `.metadata`: the column is named
                    # "metadata", but that attribute on a declarative model is
                    # SQLAlchemy's own MetaData object.
                    "metadata": cred.metadata_,
                    "pinned": link.pinned
                })

        return ApiResponse.ok({
            "profile": {
                "username": passport.username,
                "display_name": passport.display_name,
                "bio": passport.bio
            },
            "credentials": creds
        })
