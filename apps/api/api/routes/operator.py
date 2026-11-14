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

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import object_session

from api.core.config import BILLING_TIERS, DEFAULT_TIER, canonical_tier, get_tier_quota
from api.core.envelope import ApiException, ApiResponse
from api.core.principal import Principal, require_operator
from api.core.rate_limit import rate_limit
from api.models import get_db
from api.models.credential import DELIVERY_STATUSES, NOT_REQUESTED, Credential
from api.models.organization import Organization, OrgMember
from api.models.quota_change import CredentialQuotaChange
from api.routes.credentials import LIKE_ESCAPE, _like_contains
from api.services.clerk_users import ContactsUnavailable, fetch_contacts
from api.services.issuance import (
    UNLIMITED,
    credential_quota_source,
    effective_credential_quota,
    is_test_credential,
    quota_state,
)
from api.services.operator_console import (
    NEAR_LIMIT_PERCENT,
    ORG_SORTS,
    OrgFilters,
    ResendConflict,
    as_key,
    duplicate_candidates,
    duplicate_names,
    kpis,
    name_key,
    org_rows,
    possible_duplicates,
    resend_credential_email,
    resend_refusal,
    title_looks_like_email,
    usage_percent,
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
        # Both null on an override-only change.
        "previous_tier": row.previous_tier,
        "new_tier": row.new_tier,
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

@router.get("/tiers", response_model=ApiResponse[dict])
def list_tiers(principal: Principal = Depends(require_operator)):
    """Every plan an operator may move an org to, in display order.

    Not `GET /api/v1/tiers`: that is the public catalog, and it drops tiers
    with `listed: False` so the pricing page cannot sell a plan nobody can
    buy. Scale is such a tier, and it is set by hand — so the operator's plan
    control built from the public catalog had no option for it, and an org on
    Scale rendered with Community selected.
    """
    tiers = sorted(BILLING_TIERS.items(), key=lambda kv: kv[1]["order"])
    return ApiResponse.ok({
        "tiers": [
            {
                "key": key,
                "name": info["name"],
                "listed": info["listed"],
                "monthly_quota": _limit(info["monthly_quota"]),
            }
            for key, info in tiers
        ],
    })


def _offset(cursor: Optional[str], offset: int) -> int:
    """`cursor` is the opaque `next_cursor` of the previous page (an offset)."""
    if cursor is None:
        return offset
    if not cursor.isdigit():
        raise HTTPException(status_code=400, detail="Unknown cursor")
    return int(cursor)


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:  # SQLite returns naive datetimes
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.get("/orgs", response_model=ApiResponse[dict])
def list_orgs(
    q: Optional[str] = Query(default=None, max_length=100),
    tier: list[str] = Query(default=[], description="Repeat for several plans"),
    active: bool = Query(default=False, description="Only orgs that issued this month"),
    near_limit: bool = Query(default=False, description=f"Only orgs at {NEAR_LIMIT_PERCENT}% of their limit or more"),
    has_override: bool = Query(default=False),
    sort: str = Query(default="usage", pattern="^(" + "|".join(sorted(ORG_SORTS)) + ")$"),
    dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: Optional[str] = Query(default=None, description="`next_cursor` from the previous page"),
    principal: Principal = Depends(require_operator),
):
    """Orgs with their quota standing, this month's usage %, and last activity.

    Sorted by usage % (busiest first), then most recent activity, by default.
    Usage, the limit and the sort are computed in SQL — `effective_limit_sql()`
    — so a page is two queries however many orgs there are.
    """
    filters = OrgFilters(
        q=q or None, tiers=tuple(tier), active=active,
        near_limit=near_limit, has_override=has_override,
    )
    start = _offset(cursor, offset)
    with get_db() as session:
        rows, total = org_rows(
            session, filters, sort=sort, descending=dir == "desc", offset=start, limit=limit,
        )
        shared = duplicate_names(session, [org.name for org, *_ in rows])
        orgs = []
        for org, used, _effective, percent, last_at in rows:
            row = _org_row(org, int(used))
            row["usage_percent"] = None if percent is None else round(float(percent), 1)
            row["last_activity_at"] = _iso(last_at)
            row["duplicate_name"] = name_key(org.name) in shared
            orgs.append(row)

        return ApiResponse.ok({
            "orgs": orgs,
            "total": total,
            "next_cursor": str(start + limit) if start + limit < total else None,
        })


@router.get("/kpis", response_model=ApiResponse[dict])
def get_kpis(principal: Principal = Depends(require_operator)):
    """The Plans tab's four numbers: active orgs and credentials issued this
    month, orgs near their limit, and failed emails in the last 7 days."""
    with get_db() as session:
        return ApiResponse.ok(kpis(session))


@router.get("/orgs/{slug}/credential-quota", response_model=ApiResponse[dict])
def get_credential_quota(slug: str, principal: Principal = Depends(require_operator)):
    """One org's quota standing, a few facts about it, and its full change
    history, newest first."""
    with get_db() as session:
        org = _get_org(session, slug)
        all_time, last_at = (
            session.query(func.count(Credential.id), func.max(Credential.issued_at))
            .filter(Credential.org_id == org.id)
            .one()
        )
        members = session.query(func.count(OrgMember.id)).filter(OrgMember.org_id == org.id).scalar()
        state = _state(session, org)
        return ApiResponse.ok({
            **state,
            "usage_percent": _rounded(usage_percent(state["used"], state["effective"])),
            "created_at": _iso(org.created_at),
            "last_activity_at": _iso(last_at),
            "member_count": int(members or 0),
            "credentials_all_time": int(all_time or 0),
            "history": _history(session, org),
        })


def _rounded(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 1)


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

# Built from DELIVERY_STATUSES so a new state cannot be written by the
# backend and refused by this filter.
_DELIVERY_PATTERN = f"^({'|'.join(sorted(DELIVERY_STATUSES | {'attempted', 'all'}))})$"
_DELIVERY_SORTS = {
    "issued_at": Credential.issued_at,
    "delivered_at": Credential.delivered_at,
    "attempts": Credential.delivery_attempts,
    "status": Credential.delivery_status,
    "org": Organization.name,
    "recipient": Credential.recipient_name,
    "title": Credential.title,
}
_DELIVERY_SORT_PATTERN = "^(" + "|".join(sorted(_DELIVERY_SORTS)) + ")$"

#: The CSV export's ceiling. Past it the file is cut and says so in a header,
#: rather than one request reading an unbounded table.
EXPORT_MAX_ROWS = 10_000


@dataclass(frozen=True)
class _DeliveryFilters:
    org: Optional[str]
    q: Optional[str]
    since: Optional[datetime]
    until: Optional[datetime]


def _delivery_query(session, f: _DeliveryFilters):
    """Credentials joined to their org, narrowed by every filter except
    status — the status counts need the query before that one."""
    query = session.query(Credential, Organization).join(
        Organization, Organization.id == Credential.org_id
    )
    if f.org:
        target = _get_org(session, f.org)
        query = query.filter(Credential.org_id == target.id)
    if f.since:
        query = query.filter(Credential.issued_at >= f.since)
    if f.until:
        query = query.filter(Credential.issued_at <= f.until)
    needle = (f.q or "").strip()
    if needle:
        pattern = _like_contains(needle)
        query = query.filter(
            or_(
                Credential.recipient_name.ilike(pattern, escape=LIKE_ESCAPE),
                Credential.recipient_email.ilike(pattern, escape=LIKE_ESCAPE),
                Credential.title.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return query


def _with_status(query, delivery_status: str):
    if delivery_status == "attempted":
        return query.filter(Credential.delivery_status != NOT_REQUESTED)
    if delivery_status != "all":
        return query.filter(Credential.delivery_status == delivery_status)
    return query


def _status_counts(query) -> dict:
    """{status: n} for the filtered rows, plus the two composite filters the
    dropdown offers. One grouped query."""
    counts = dict(
        query.with_entities(Credential.delivery_status, func.count(Credential.id))
        .group_by(Credential.delivery_status)
        .all()
    )
    counts = {k: int(v) for k, v in counts.items()}
    counts["all"] = sum(counts.values())
    counts["attempted"] = counts["all"] - counts.get(NOT_REQUESTED, 0)
    return counts


def _ordered(query, sort: str, descending: bool):
    column = _DELIVERY_SORTS[sort]
    primary = [column.is_(None), column.desc() if descending else column.asc()]
    # (issued_at, public_id) as the tie-break, so equal keys page stably.
    return query.order_by(*primary, Credential.issued_at.desc(), Credential.public_id.desc())


def _delivery_filters(org, q, since, until) -> _DeliveryFilters:
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="`since` must be before `until`")
    return _DeliveryFilters(org=org, q=q, since=since, until=until)


@router.get("/deliveries", response_model=ApiResponse[dict])
def list_deliveries(
    org: Optional[str] = Query(default=None, max_length=100, description="An org slug; omit for every org"),
    q: Optional[str] = Query(default=None, max_length=200, description="Recipient name, email or title"),
    delivery_status: str = Query(default="attempted", pattern=_DELIVERY_PATTERN),
    since: Optional[datetime] = Query(default=None, description="Issued at or after (ISO 8601)"),
    until: Optional[datetime] = Query(default=None, description="Issued at or before (ISO 8601)"),
    sort: str = Query(default="issued_at", pattern=_DELIVERY_SORT_PATTERN),
    dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: Optional[str] = Query(default=None, description="The last id of the previous page (default sort only)"),
    principal: Principal = Depends(require_operator),
):
    """Every credential email across every org: who issued it, to whom, and
    what became of the send. Newest first by default.

    `attempted` (the default) is every row where a send was tried or may have
    been — everything but `not_requested`. `unknown` rows predate delivery
    tracking and are reported as such, never guessed.

    `counts` is the number of rows per status under the other filters, for
    the status dropdown. Each row carries `resendable` (the operator resend
    rule, `resend_refusal()`) and two read-only data-quality flags,
    `title_looks_like_email` and `possible_duplicate`.

    Paged by `offset`. `cursor` (keyset on issued_at, public_id) still works
    for the default sort, for callers that page newest-first.
    """
    filters = _delivery_filters(org, q, since, until)
    with get_db() as session:
        base = _delivery_query(session, filters)
        counts = _status_counts(base)
        query = _with_status(base, delivery_status)
        total = counts.get(delivery_status, 0)

        default_sort = sort == "issued_at" and dir == "desc"
        if cursor:
            if not default_sort:
                raise HTTPException(status_code=400, detail="`cursor` pages the default sort only; use `offset`")
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
            next_cursor = rows[-1][0].public_id if has_more else None
        else:
            rows = _ordered(query, sort, dir == "desc").offset(offset).limit(limit).all()
            has_more = offset + len(rows) < total
            next_cursor = rows[-1][0].public_id if has_more and default_sort and rows else None

        creds = [c for c, _ in rows]
        dupes = possible_duplicates([as_key(c) for c in creds], duplicate_candidates(session, creds))

        return ApiResponse.ok({
            "deliveries": [_delivery_row(c, o, dupes) for c, o in rows],
            "total": total,
            "counts": counts,
            "offset": offset if not cursor else None,
            "next_cursor": next_cursor,
        })


def _delivery_row(c: Credential, o: Organization, dupes: set[str]) -> dict:
    refusal = resend_refusal(c, session=object_session(c))
    return {
        "id": c.public_id,
        "org_slug": o.slug,
        "org_name": o.name,
        "recipient_name": c.recipient_name,
        "recipient_email": c.recipient_email or None,
        "title": c.title,
        "status": c.status,
        "is_test": is_test_credential(c),
        "issued_at": _iso(c.issued_at),
        "delivery_status": c.delivery_status,
        "delivered_at": _iso(c.delivered_at),
        "delivery_attempts": c.delivery_attempts,
        "delivery_error": c.delivery_error,
        # Only while deferred: when the email goes out without anyone asking.
        "delivery_next_attempt_at": _iso(c.delivery_next_attempt_at),
        "resendable": refusal is None,
        # Why not, in words, so a failed row without a Resend button explains
        # itself instead of looking broken.
        "resend_refusal": refusal,
        "title_looks_like_email": title_looks_like_email(c.title),
        "possible_duplicate": c.public_id in dupes,
    }


_CSV_COLUMNS = [
    ("id", "Credential"),
    ("org_slug", "Org slug"),
    ("org_name", "Org"),
    ("recipient_name", "Recipient"),
    ("recipient_email", "Email"),
    ("title", "Title"),
    ("status", "Credential status"),
    ("is_test", "Test"),
    ("issued_at", "Issued at"),
    ("delivery_status", "Email status"),
    ("delivered_at", "Sent at"),
    ("delivery_attempts", "Attempts"),
    ("delivery_error", "Error"),
]


def _csv_cell(value) -> str:
    """A cell a spreadsheet will not execute. Recipient names and titles are
    customer input; `=HYPERLINK(...)` in one is a formula on the operator's
    machine unless it is defused."""
    text = "" if value is None else str(value)
    if text and text[0] in "=+-@\t\r":
        return "'" + text
    return text


@router.get("/deliveries/export")
def export_deliveries(
    org: Optional[str] = Query(default=None, max_length=100),
    q: Optional[str] = Query(default=None, max_length=200),
    delivery_status: str = Query(default="attempted", pattern=_DELIVERY_PATTERN),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    sort: str = Query(default="issued_at", pattern=_DELIVERY_SORT_PATTERN),
    dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    principal: Principal = Depends(require_operator),
):
    """The current filtered deliveries view as CSV, in the view's order.

    At most `EXPORT_MAX_ROWS` rows; when there were more,
    `X-Export-Truncated: true` says so and `X-Export-Total` gives the count.
    Contains recipient personal data, so it is operator-only like every route
    here, and is never cached.
    """
    filters = _delivery_filters(org, q, since, until)
    with get_db() as session:
        query = _with_status(_delivery_query(session, filters), delivery_status)
        total = query.count()
        rows = _ordered(query, sort, dir == "desc").limit(EXPORT_MAX_ROWS).all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([label for _, label in _CSV_COLUMNS])
        for c, o in rows:
            row = _delivery_row(c, o, set())
            writer.writerow([_csv_cell(row[key]) for key, _ in _CSV_COLUMNS])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="certforge-deliveries-{stamp}.csv"',
            "Cache-Control": "no-store",
            "X-Export-Total": str(total),
            "X-Export-Truncated": "true" if total > EXPORT_MAX_ROWS else "false",
            "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Total, X-Export-Truncated",
        },
    )


@router.post(
    "/deliveries/{public_id}/resend",
    response_model=ApiResponse[dict],
    # Every call can mail a third party, so it is bounded per minute as well
    # as by the per-credential attempt ceiling and the idempotency key.
    dependencies=[Depends(rate_limit())],
)
def resend_delivery(
    public_id: str,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=8, max_length=100,
        description="One per confirmation. A repeat is answered from the first request, not resent.",
    ),
    principal: Principal = Depends(require_operator),
):
    """Resend one credential's email: a failed send, or a pending/unknown one
    older than an hour. Through `resend_credential()`, the same path as the
    org dashboard's resend, so it increments `delivery_attempts` and respects
    the attempt ceiling. Recorded in `operator_actions` under the operator's id.

    Idempotent on `Idempotency-Key`: a double-click sends once, and the second
    request gets the first one's answer with `replayed: true`.
    """
    try:
        return ApiResponse.ok(
            resend_credential_email(
                public_id, actor=principal.clerk_user_id, idempotency_key=idempotency_key,
            )
        )
    except ResendConflict as exc:
        code = 404 if exc.error_type == "not_found" else 409
        raise ApiException(code, exc.message, error_type=exc.error_type)
