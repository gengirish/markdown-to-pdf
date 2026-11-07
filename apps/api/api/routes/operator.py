"""CertForge staff screens: an org's credential quota, and its plan.

W2 of docs/operator-quota-overrides-plan.md, plus the manual plan change its
Decision 4 anticipates. Checkout is still mocked, so an org at a tier gate has
no self-serve way up; before this, "moved by hand" meant SQL against
production, and SQL had to remember that the gates read `tier` while issuance
read `monthly_quota`.

Every route depends on `require_operator` — an allowlist of verified Clerk
user ids, never an org role and never an API key. Every write goes through
`services/plans.py`, which logs it in the same transaction. Contact details
are read from Clerk on request (`services/clerk_users.py`) and never stored.

Not public, so deliberately absent from `_build_llms_txt` / `_build_sitemap_xml`.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_

from api.core.config import BILLING_TIERS, DEFAULT_TIER, canonical_tier, get_tier_quota
from api.core.envelope import ApiException, ApiResponse
from api.core.principal import Principal, require_operator
from api.models import get_db
from api.models.credential import NOT_REQUESTED, Credential
from api.models.organization import Organization, OrgMember
from api.models.quota_change import CredentialQuotaChange
from api.models.usage import UsageLedger
from api.routes.credentials import LIKE_ESCAPE, _like_contains
from api.services.clerk_users import ContactsUnavailable, fetch_contacts
from api.services.issuance import (
    UNLIMITED,
    credential_quota_source,
    effective_credential_quota,
    is_test_credential,
    quota_state,
)
from api.services.plans import (
    MAX_CREDENTIAL_QUOTA_OVERRIDE,
    MIN_REASON_LENGTH,
    change_tier,
    set_credential_quota_override,
)

router = APIRouter(prefix="/operator", tags=["operator"])


# -- wire shapes ---------------------------------------------------------------
#
# -1 is the unlimited sentinel inside the process and `null` on the wire, as in
# `_meter()` and `tier_catalog()`. An override has a third state — none at all —
# so it travels as an object: `null` means no override, `{"limit": null}` means
# an unlimited one. A bare `null` could not tell those apart.

def _limit(value: int) -> Optional[int]:
    return None if value == UNLIMITED else value


def _override(value: Optional[int]) -> Optional[dict]:
    return None if value is None else {"limit": _limit(value)}


def _get_org(session, slug: str) -> Organization:
    org = session.query(Organization).filter_by(slug=slug).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _org_row(org: Organization, used: int) -> dict:
    return {
        "slug": org.slug,
        "name": org.name,
        "tier": org.tier,
        "tier_name": BILLING_TIERS.get(org.tier, BILLING_TIERS[DEFAULT_TIER])["name"],
        "tier_known": org.tier in BILLING_TIERS,
        "tier_quota": _limit(get_tier_quota(org.tier)),
        "source": credential_quota_source(org),
        "override": _override(org.credential_quota_override),
        "effective": _limit(effective_credential_quota(org)),
        "used": used,
    }


def _state(session, org: Organization) -> dict:
    _, used = quota_state(session, org)
    return _org_row(org, used)


def _change(row: CredentialQuotaChange) -> dict:
    return {
        "previous_override": _override(row.previous_override),
        "new_override": _override(row.new_override),
        "effective_before": _limit(row.effective_before),
        "effective_after": _limit(row.effective_after),
        "reason": row.reason,
        "actor": row.actor,
        "created_at": row.created_at.isoformat(),
    }


def _history(session, org: Organization) -> list[dict]:
    rows = (
        session.query(CredentialQuotaChange)
        .filter_by(org_id=org.id)
        .order_by(CredentialQuotaChange.created_at.desc())
        .all()
    )
    return [_change(r) for r in rows]


class _Reasoned(BaseModel):
    #: Required: the question this answers is "why does acme get 5,000?",
    #: asked six months from now.
    reason: str = Field(max_length=1000)

    @field_validator("reason")
    @classmethod
    def _long_enough(cls, value: str) -> str:
        value = value.strip()
        if len(value) < MIN_REASON_LENGTH:
            raise ValueError(f"reason must be at least {MIN_REASON_LENGTH} characters")
        return value


class QuotaOverride(_Reasoned):
    #: Required, and `null` means unlimited. Removing the override is DELETE.
    limit: Optional[int] = Field(..., ge=0, le=MAX_CREDENTIAL_QUOTA_OVERRIDE)


class QuotaOverrideRemoval(_Reasoned):
    pass


class TierChange(_Reasoned):
    tier: str


# -- routes --------------------------------------------------------------------

@router.get("/orgs", response_model=ApiResponse[dict])
def list_orgs(
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: Optional[str] = Query(default=None, description="The last slug of the previous page"),
    principal: Principal = Depends(require_operator),
):
    """Orgs whose slug or name matches `q`, by slug, with their quota standing."""
    with get_db() as session:
        query = session.query(Organization)
        if q:
            pattern = f"%{q}%"
            query = query.filter(
                or_(Organization.slug.ilike(pattern), Organization.name.ilike(pattern))
            )
        if cursor:
            query = query.filter(Organization.slug > cursor)
        orgs = query.order_by(Organization.slug).limit(limit + 1).all()
        has_more = len(orgs) > limit
        orgs = orgs[:limit]

        # One ledger read for the page rather than one per row.
        period = UsageLedger.current_period()
        used = {
            ledger.org_id: ledger.credentials_issued
            for ledger in session.query(UsageLedger).filter(
                UsageLedger.period == period,
                UsageLedger.org_id.in_([o.id for o in orgs]),
            )
        } if orgs else {}

        return ApiResponse.ok({
            "orgs": [_org_row(o, used.get(o.id, 0)) for o in orgs],
            "next_cursor": orgs[-1].slug if has_more else None,
        })


@router.get("/orgs/{slug}/credential-quota", response_model=ApiResponse[dict])
def get_credential_quota(slug: str, principal: Principal = Depends(require_operator)):
    """One org's quota standing and its full change history, newest first."""
    with get_db() as session:
        org = _get_org(session, slug)
        return ApiResponse.ok({**_state(session, org), "history": _history(session, org)})


_ROLE_ORDER = {"owner": 0, "admin": 1, "issuer": 2}


@router.get("/orgs/{slug}/contacts", response_model=ApiResponse[dict])
def get_contacts(slug: str, principal: Principal = Depends(require_operator)):
    """Who to reach at an org: its members, owners first, with the email and
    phone Clerk holds for each.

    Separate from the quota read on purpose. Contact details come from Clerk's
    Backend API, and a Clerk failure answers 503 here without taking the
    quota controls down with it. `null` means Clerk has no such value; a member
    Clerk does not know at all is still listed, with `found: false`.
    """
    with get_db() as session:
        org = _get_org(session, slug)
        members = [
            (m.clerk_user_id, m.role)
            for m in session.query(OrgMember).filter_by(org_id=org.id)
        ]

    members.sort(key=lambda m: (_ROLE_ORDER.get(m[1], len(_ROLE_ORDER)), m[0]))
    try:
        found = fetch_contacts([uid for uid, _ in members])
    except ContactsUnavailable as exc:
        raise ApiException(503, str(exc), error_type="contacts_unavailable")

    return ApiResponse.ok({
        "contacts": [
            {
                "clerk_user_id": uid,
                "role": role,
                "found": uid in found,
                **found.get(uid, {"name": None, "email": None, "phone": None}),
            }
            for uid, role in members
        ],
    })


@router.put("/orgs/{slug}/credential-quota", response_model=ApiResponse[dict])
def set_credential_quota(
    slug: str,
    payload: QuotaOverride,
    principal: Principal = Depends(require_operator),
):
    """Give one org its own credential limit. `limit: null` is unlimited.

    A limit below what the org has already issued this month is allowed — an
    operator may need to stop an org — and the response says by how much in
    `over_by`. The dashboard asks for confirmation before sending one.
    """
    override = UNLIMITED if payload.limit is None else payload.limit
    with get_db() as session:
        org = _get_org(session, slug)
        row = set_credential_quota_override(
            session, org, override,
            actor=principal.clerk_user_id, reason=payload.reason,
        )
        session.flush()

        data = {**_state(session, org), "changed": row is not None}
        if override == get_tier_quota(org.tier):
            data["note"] = (
                "This override equals the tier's quota. It freezes the org at "
                "that number even if the tier's quota changes later."
            )
        if override != UNLIMITED and data["used"] > override:
            data["over_by"] = data["used"] - override
        return ApiResponse.ok(data)


@router.delete("/orgs/{slug}/credential-quota", response_model=ApiResponse[dict])
def clear_credential_quota(
    slug: str,
    payload: QuotaOverrideRemoval,
    principal: Principal = Depends(require_operator),
):
    """Remove the override, so the org follows its tier's quota again."""
    with get_db() as session:
        org = _get_org(session, slug)
        row = set_credential_quota_override(
            session, org, None,
            actor=principal.clerk_user_id, reason=payload.reason,
        )
        session.flush()
        return ApiResponse.ok({**_state(session, org), "changed": row is not None})


@router.put("/orgs/{slug}/tier", response_model=ApiResponse[dict])
def set_tier(
    slug: str,
    payload: TierChange,
    principal: Principal = Depends(require_operator),
):
    """Move one org to another plan without payment, up or down.

    Through `change_tier()`, the same function the Razorpay webhook calls, so
    a manual plan change follows the same rule: it clears any credential
    override, and logs that it did. Nothing already acquired is taken away on
    a downgrade — the entitlement gates run where a capability is acquired,
    not where it is used.
    """
    # Resolved first: an operator working from an older runbook types the name
    # the plan was sold under, and storing that retired name in `tier` is worse
    # than a 422 — it is a row that only reads correctly through the alias.
    tier = canonical_tier(payload.tier)
    if tier not in BILLING_TIERS:
        raise ApiException(
            422,
            f"Unknown tier {payload.tier!r}",
            error_type="unknown_tier",
            details={"tiers": list(BILLING_TIERS)},
        )
    with get_db() as session:
        org = _get_org(session, slug)
        previous_tier = org.tier
        had_override = org.credential_quota_override is not None
        changed = change_tier(
            session, org, tier,
            actor=principal.clerk_user_id, reason=payload.reason,
        )
        session.flush()
        return ApiResponse.ok({
            **_state(session, org),
            "previous_tier": previous_tier,
            "changed": changed,
            "override_cleared": changed and had_override,
        })


# -- who each org has emailed -----------------------------------------------------

_DELIVERY_PATTERN = "^(attempted|not_requested|pending|sent|failed|unknown|all)$"


@router.get("/deliveries", response_model=ApiResponse[dict])
def list_deliveries(
    org: Optional[str] = Query(default=None, max_length=100, description="An org slug; omit for every org"),
    q: Optional[str] = Query(default=None, max_length=200, description="Recipient name, email or title"),
    delivery_status: str = Query(default="attempted", pattern=_DELIVERY_PATTERN),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None, description="The last id of the previous page"),
    principal: Principal = Depends(require_operator),
):
    """Every credential email across every org: who issued it, to whom, and
    what became of the send. Newest first.

    `attempted` (the default) is every row where a send was tried or may have
    been — everything but `not_requested`. `unknown` rows predate delivery
    tracking and are reported as such, never guessed. Read-only.
    """
    with get_db() as session:
        query = session.query(Credential, Organization).join(
            Organization, Organization.id == Credential.org_id
        )
        if org:
            target = _get_org(session, org)
            query = query.filter(Credential.org_id == target.id)
        if delivery_status == "attempted":
            query = query.filter(Credential.delivery_status != NOT_REQUESTED)
        elif delivery_status != "all":
            query = query.filter(Credential.delivery_status == delivery_status)
        needle = (q or "").strip()
        if needle:
            pattern = _like_contains(needle)
            query = query.filter(
                or_(
                    Credential.recipient_name.ilike(pattern, escape=LIKE_ESCAPE),
                    Credential.recipient_email.ilike(pattern, escape=LIKE_ESCAPE),
                    Credential.title.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )

        total = query.count()
        if cursor:
            anchor = session.query(Credential).filter_by(public_id=cursor).first()
            if anchor is None:
                raise HTTPException(status_code=400, detail="Unknown cursor")
            # (issued_at, public_id) so a bulk batch issued in one instant is
            # neither skipped nor repeated at a page boundary.
            query = query.filter(
                or_(
                    Credential.issued_at < anchor.issued_at,
                    and_(
                        Credential.issued_at == anchor.issued_at,
                        Credential.public_id < anchor.public_id,
                    ),
                )
            )
        rows = (
            query.order_by(Credential.issued_at.desc(), Credential.public_id.desc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]

        return ApiResponse.ok({
            "deliveries": [
                {
                    "id": c.public_id,
                    "org_slug": o.slug,
                    "org_name": o.name,
                    "recipient_name": c.recipient_name,
                    "recipient_email": c.recipient_email or None,
                    "title": c.title,
                    "status": c.status,
                    "is_test": is_test_credential(c),
                    "issued_at": c.issued_at.isoformat(),
                    "delivery_status": c.delivery_status,
                    "delivered_at": c.delivered_at.isoformat() if c.delivered_at else None,
                    "delivery_attempts": c.delivery_attempts,
                    "delivery_error": c.delivery_error,
                }
                for c, o in rows
            ],
            "total": total,
            "next_cursor": rows[-1][0].public_id if has_more else None,
        })
