"""What an organization's plan lets it do, and the refusals when it does not.

The template allowance lives in `routes/templates.py` because it predates this
module; everything else a tier grants is enforced here, read off the one table
in `core/config.py` (`BILLING_TIERS`).

This exists because the pricing page sold CSV bulk issuance, artwork upload and
API keys as Starter features while the API granted all three to every tier. A
line on the pricing page that nothing enforces is a page and an API that
disagree — the same shape as the template gate before it had a count.

Every refusal is a 402 carrying its own `error.type`, for the reason
`_enforce_template_limit` gives: a credential-quota refusal is also a 402, and
the dashboard has to be able to tell them apart.
"""

from datetime import datetime, timezone

from sqlalchemy import func

from api.core.config import (
    TIER_GRANTS,
    get_tier,
    get_tier_csv_batch_limit,
    listed_tiers,
    tier_grants,
)
from api.core.envelope import ApiException
from api.services.issuance import UNLIMITED


def _tiers_in_order():
    return listed_tiers()


def _plan_name(org) -> str:
    return get_tier(org.tier)["name"]


def require_grant(org, grant: str) -> None:
    """Refuse with 402 unless the org's tier includes `grant` (see TIER_GRANTS).

    Checked where the capability is *acquired* — an upload, a new key — never
    where something already acquired is used. An org moved down a tier keeps
    rendering the artwork its credentials were issued on and keeps its existing
    keys working; taking those away would break documents and integrations
    that were valid when they were made.
    """
    if tier_grants(org.tier, grant):
        return

    what = TIER_GRANTS[grant]
    upgrades = [
        {"tier": key, "name": info["name"]}
        for key, info in _tiers_in_order()
        if info[grant]
    ]
    first = upgrades[0]["name"] if upgrades else "a paid plan"
    raise ApiException(
        402,
        f"{what} is not included in the {_plan_name(org)} plan. "
        f"It starts on {first}.",
        error_type="plan_feature_required",
        details={
            "tier": org.tier,
            "tier_name": _plan_name(org),
            "feature": grant,
            "upgrades": upgrades,
        },
    )


def month_start(now: datetime | None = None) -> datetime:
    """The first instant of the current UTC calendar month — the same period
    `UsageLedger.current_period()` names."""
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def csv_batches_this_month(session, org) -> int:
    """CSV batches this org has uploaded since the start of the UTC month.

    Counted off `credential_batches` rather than a ledger column: a batch row
    is only committed when the upload succeeds, so the row count is already
    the number that should be metered, and there is no counter to drift.
    """
    from api.models.credential import CredentialBatch

    return (
        session.query(func.count(CredentialBatch.id))
        .filter(
            CredentialBatch.org_id == org.id,
            CredentialBatch.created_at >= month_start(),
        )
        .scalar()
        or 0
    )


def enforce_csv_batch_limit(session, org) -> None:
    """Refuse a CSV upload once the org has used its tier's batches this month."""
    limit = get_tier_csv_batch_limit(org.tier)
    if limit == UNLIMITED:
        return

    used = csv_batches_this_month(session, org)
    if used < limit:
        return

    upgrades = [
        {
            "tier": key,
            "name": info["name"],
            "csv_batch_limit": (
                None if info["csv_batch_limit"] == UNLIMITED else info["csv_batch_limit"]
            ),
        }
        for key, info in _tiers_in_order()
        if info["csv_batch_limit"] == UNLIMITED or info["csv_batch_limit"] > limit
    ]

    raise ApiException(
        402,
        f"This organization is on the {_plan_name(org)} plan, which includes "
        f"{limit} CSV upload{'' if limit == 1 else 's'} a month, and it has been "
        f"used. Single credentials can still be issued from the dashboard, or "
        f"move to a larger plan for unlimited uploads.",
        error_type="csv_batch_limit_reached",
        details={
            "tier": org.tier,
            "tier_name": _plan_name(org),
            "limit": limit,
            "used": used,
            "upgrades": upgrades,
        },
    )
