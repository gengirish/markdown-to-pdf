"""The only code that writes an organization's tier or credential override.

Two things change what an org may issue: the plan it is on, and an operator's
override of that plan's credential quota. Both are written here and nowhere
else, because each write has a rule attached that a second writer would
forget:

- A plan change clears the override (Decision 4 of
  docs/operator-quota-overrides-plan.md), and says so in the change log. An
  org given 1,000 on Community that pays for Growth goes to 2,000 without
  anyone having to notice.
- Every override change is logged, with a reason, in the same transaction.
- `monthly_quota` is kept equal to the effective limit on every write, so a
  rollback to code that still reads it finds a current number. Until W4.

Nothing here commits. The caller's transaction is what makes the change and
its log row land together or not at all.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.core.config import BILLING_TIERS
from api.models.organization import Organization
from api.models.quota_change import CredentialQuotaChange
from api.services.issuance import effective_credential_quota

logger = logging.getLogger(__name__)

#: A reason has to be long enough to answer "why?" six months later.
MIN_REASON_LENGTH = 10

#: The largest override an operator may set. It catches a mistyped extra zero;
#: it is not a policy.
MAX_CREDENTIAL_QUOTA_OVERRIDE = 1_000_000


class UnknownTier(ValueError):
    """A tier BILLING_TIERS does not know. Refused rather than stored:
    `get_tier()` would treat it as Community everywhere, so the write would
    report success and grant nothing — which is what the old webhook's
    `"pro"` did for months."""


def _log_override_change(
    session,
    org: Organization,
    *,
    previous_override: Optional[int],
    effective_before: int,
    actor: str,
    reason: str,
) -> CredentialQuotaChange:
    row = CredentialQuotaChange(
        org_id=org.id,
        previous_override=previous_override,
        new_override=org.credential_quota_override,
        effective_before=effective_before,
        effective_after=effective_credential_quota(org),
        reason=reason,
        actor=actor,
    )
    session.add(row)
    return row


def change_tier(
    session,
    org: Organization,
    new_tier: str,
    *,
    actor: str,
    reason: Optional[str] = None,
) -> bool:
    """Move `org` to `new_tier`. Returns False when it was already there.

    - **Only a real change does anything.** Razorpay retries deliveries, and a
      repeated `subscription.activated` for the plan the org already has must
      not wipe an override an operator set since.
    - **Up or down, it clears the override.** One rule: the plan changed.
    - **The clear is logged** under `actor`. No override, no row — the
      override did not change.
    """
    if new_tier not in BILLING_TIERS:
        raise UnknownTier(new_tier)
    if new_tier == org.tier:
        return False

    previous_tier = org.tier
    previous_override = org.credential_quota_override
    effective_before = effective_credential_quota(org)

    org.tier = new_tier
    org.credential_quota_override = None
    org.monthly_quota = effective_credential_quota(org)

    detail = f"Plan changed from {previous_tier} to {new_tier}"
    if previous_override is not None:
        _log_override_change(
            session,
            org,
            previous_override=previous_override,
            effective_before=effective_before,
            actor=actor,
            reason=f"{detail}: {reason}" if reason else detail,
        )

    logger.warning(
        "Tier change: org=%s %s -> %s by %s (override %s cleared) reason=%r",
        org.slug, previous_tier, new_tier, actor,
        "was" if previous_override is not None else "not", reason,
    )
    return True


def set_credential_quota_override(
    session,
    org: Organization,
    override: Optional[int],
    *,
    actor: str,
    reason: str,
) -> Optional[CredentialQuotaChange]:
    """Set (`override` an int, -1 for unlimited) or remove (`None`) the
    override. Returns the change-log row, or None when nothing changed.

    Validation of the value and the reason belongs to the caller's request
    model; this re-checks the invariants a future second caller could miss.
    """
    if override is not None and not (
        override == -1 or 0 <= override <= MAX_CREDENTIAL_QUOTA_OVERRIDE
    ):
        raise ValueError(f"credential quota override out of range: {override}")
    if len(reason.strip()) < MIN_REASON_LENGTH:
        raise ValueError("a reason of at least 10 characters is required")

    if override == org.credential_quota_override:
        return None

    previous_override = org.credential_quota_override
    effective_before = effective_credential_quota(org)

    org.credential_quota_override = override
    org.monthly_quota = effective_credential_quota(org)

    row = _log_override_change(
        session,
        org,
        previous_override=previous_override,
        effective_before=effective_before,
        actor=actor,
        reason=reason.strip(),
    )
    logger.warning(
        "Credential quota override: org=%s %r -> %r by %s reason=%r",
        org.slug, previous_override, override, actor, reason,
    )
    return row
