"""The claim token: proof that a claimant was sent the credential's email.

A credential's public ID is not a secret. It is in the QR code, on
`/verify/{id}` and in every badge URL, so a claim keyed on the ID alone lets
whoever sees a certificate first put it in their own passport and lock the
recipient out. The token is what only the delivery email carries.

It is stateless, like every other signed URL in this codebase: an HMAC of the
public ID, so a retried or resent email rebuilds the same link from the row
alone and nothing has to be stored. See
`docs/claim-link-and-webhook-retries-plan.md`, Part A.
"""

import hashlib
import hmac

#: 32 hex characters, 128 bits: unguessable, and short enough that the link
#: does not wrap in a mail client.
TOKEN_LENGTH = 32


def claim_token_for(public_id: str) -> str:
    # Read at call time so a test can swap the secret. The "claim:" prefix
    # scopes the MAC, so a claim token can never double as another signature
    # made with the same key.
    from api.core import config

    return hmac.new(
        config.CLAIM_SECRET.encode(), f"claim:{public_id}".encode(), hashlib.sha256
    ).hexdigest()[:TOKEN_LENGTH]


def claim_token_valid(public_id: str, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(token.encode(), claim_token_for(public_id).encode())


def claim_url_for(public_id: str) -> str:
    """The link in the email. CERTFORGE_WEB_URL, never SITE_URL — the claim
    page is part of the CertForge dashboard, not the legacy product."""
    from api.core import config

    return f"{config.CERTFORGE_WEB_URL}/claim/{public_id}?t={claim_token_for(public_id)}"
