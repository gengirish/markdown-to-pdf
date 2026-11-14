"""The operator console's reads, and its one new write: resending an email.

Everything here is aggregated in SQL so the console never pulls a table into
the browser or walks orgs one query at a time:

- `effective_limit_sql()` is `effective_credential_quota()` written as a SQL
  expression, so the org list can sort and filter by usage % in the database.
  It is a second implementation of the one rule that matters most here, so
  `test_operator_console.py` checks the two against each other for every
  tier, every alias, an unknown tier and an override. If you change one,
  that test is what tells you to change the other.
- `possible_duplicates()` is pure, so its rule is tested without a database.

Read-only apart from `resend_credential_email()`, which goes through the same
`resend_credential()` the org dashboard uses and records itself in
`operator_actions`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError

from api.core.config import BILLING_TIERS, DEFAULT_TIER, TIER_ALIASES
from api.models import get_db
from api.models.credential import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_UNKNOWN,
    REVOKED,
    Credential,
)
from api.models.operator_action import FAILED, REFUSED, STARTED, SUCCEEDED, OperatorAction
from api.models.organization import Organization
from api.models.usage import UsageLedger
from api.services.delivery import MAX_DELIVERY_ATTEMPTS
from api.services.issuance import (
    UNLIMITED,
    IssuanceError,
    email_paused_refusal,
    is_test_credential,
    resend_credential,
)

#: "Near limit" on the KPI strip and the table's filter chip.
NEAR_LIMIT_PERCENT = 80

#: A pending or unknown send may be resent once it has had this long to land.
RESEND_GRACE = timedelta(hours=1)

#: The window in which a second credential to the same person looks like a mistake.
DUPLICATE_WINDOW = timedelta(days=7)

RESEND_ACTION = "resend_credential_email"


# -- the enforced limit, in SQL --------------------------------------------------

def _tier_quota_map() -> dict[str, int]:
    """Every stored `tier` value the table resolves, aliases included."""
    quotas = {key: info["monthly_quota"] for key, info in BILLING_TIERS.items()}
    for alias, target in TIER_ALIASES.items():
        quotas.setdefault(alias, BILLING_TIERS[target]["monthly_quota"])
    return quotas


def tier_quota_sql():
    """`get_tier_quota(Organization.tier)`: aliases resolved, unknown → Community."""
    return case(
        _tier_quota_map(),
        value=Organization.tier,
        else_=BILLING_TIERS[DEFAULT_TIER]["monthly_quota"],
    )


def effective_limit_sql():
    """`effective_credential_quota(org)`: the override if set, else the tier's.
    -1 means unlimited, as in Python."""
    return func.coalesce(Organization.credential_quota_override, tier_quota_sql())


def usage_percent_sql(used, limit):
    """Used as a percentage of the limit. NULL for unlimited. A limit of 0 is
    100% — an org stopped by an override of 0 is at its limit, not fine."""
    return case(
        (limit == UNLIMITED, None),
        (limit == 0, 100.0),
        else_=used * 100.0 / limit,
    )


def usage_percent(used: int, limit: Optional[int]) -> Optional[float]:
    """The same rule in Python, for one row. `limit` None is unlimited."""
    if limit is None or limit == UNLIMITED:
        return None
    if limit == 0:
        return 100.0
    return used * 100.0 / limit


# -- the org list ------------------------------------------------------------------

@dataclass(frozen=True)
class OrgFilters:
    q: Optional[str] = None
    tiers: tuple[str, ...] = ()
    active: bool = False
    near_limit: bool = False
    has_override: bool = False


ORG_SORTS = {"usage", "name", "plan", "limit", "used", "last_activity", "slug"}


def org_rows(session, filters: OrgFilters, *, sort: str = "usage", descending: bool = True,
             offset: int = 0, limit: int = 25):
    """One page of orgs with this month's usage, enforced limit, usage %, and
    last activity, plus the total matching. Two queries, whatever the page size."""
    period = UsageLedger.current_period()
    used = func.coalesce(UsageLedger.credentials_issued, 0)
    effective = effective_limit_sql()
    percent = usage_percent_sql(used, effective)

    activity = (
        select(Credential.org_id, func.max(Credential.issued_at).label("last_at"))
        .group_by(Credential.org_id)
        .subquery()
    )

    query = (
        session.query(
            Organization,
            used.label("used"),
            effective.label("effective"),
            percent.label("percent"),
            activity.c.last_at,
        )
        .outerjoin(
            UsageLedger,
            and_(UsageLedger.org_id == Organization.id, UsageLedger.period == period),
        )
        .outerjoin(activity, activity.c.org_id == Organization.id)
    )

    if filters.q:
        pattern = f"%{filters.q}%"
        query = query.filter(or_(Organization.slug.ilike(pattern), Organization.name.ilike(pattern)))
    if filters.tiers:
        stored = set(filters.tiers) | {a for a, t in TIER_ALIASES.items() if t in filters.tiers}
        query = query.filter(Organization.tier.in_(sorted(stored)))
    if filters.active:
        query = query.filter(used > 0)
    if filters.near_limit:
        query = query.filter(percent >= NEAR_LIMIT_PERCENT)
    if filters.has_override:
        query = query.filter(Organization.credential_quota_override.isnot(None))

    total = query.count()

    def ordered(expr):
        # NULLs last in both directions, spelled out: SQLite and Postgres
        # disagree on the default.
        return [expr.is_(None), expr.desc() if descending else expr.asc()]

    if sort == "name":
        order = [func.lower(Organization.name).desc() if descending else func.lower(Organization.name).asc()]
    elif sort == "slug":
        order = [Organization.slug.desc() if descending else Organization.slug.asc()]
    elif sort == "plan":
        order = [Organization.tier.desc() if descending else Organization.tier.asc()]
    elif sort == "limit":
        # Unlimited sorts as the largest limit.
        big = case((effective == UNLIMITED, 2**31 - 1), else_=effective)
        order = [big.desc() if descending else big.asc()]
    elif sort == "used":
        order = [used.desc() if descending else used.asc()]
    elif sort == "last_activity":
        order = ordered(activity.c.last_at)
    else:  # usage: the default, busiest first, then most recently active
        order = ordered(percent) + [activity.c.last_at.is_(None), activity.c.last_at.desc()]
    order.append(Organization.slug.asc())

    rows = query.order_by(*order).offset(offset).limit(limit).all()
    return rows, total


def duplicate_names(session, names: Iterable[str]) -> set[str]:
    """Which of these org display names (case- and space-insensitive) are
    shared by more than one org. One grouped query over the page's names."""
    keys = {n.strip().lower() for n in names if n}
    if not keys:
        return set()
    key = func.lower(func.trim(Organization.name))
    rows = (
        session.query(key)
        .filter(key.in_(sorted(keys)))
        .group_by(key)
        .having(func.count(Organization.id) > 1)
        .all()
    )
    return {r[0] for r in rows}


def name_key(name: str) -> str:
    return (name or "").strip().lower()


# -- KPIs --------------------------------------------------------------------------

def kpis(session, *, now: Optional[datetime] = None) -> dict:
    """The four numbers on the Plans tab. Four aggregate queries, no rows."""
    now = now or datetime.now(timezone.utc)
    period = now.strftime("%Y-%m")

    active, issued = (
        session.query(
            func.count(UsageLedger.org_id),
            func.coalesce(func.sum(UsageLedger.credentials_issued), 0),
        )
        .filter(UsageLedger.period == period, UsageLedger.credentials_issued > 0)
        .one()
    )

    used = func.coalesce(UsageLedger.credentials_issued, 0)
    percent = usage_percent_sql(used, effective_limit_sql())
    near = (
        session.query(func.count(Organization.id))
        .outerjoin(
            UsageLedger,
            and_(UsageLedger.org_id == Organization.id, UsageLedger.period == period),
        )
        .filter(percent >= NEAR_LIMIT_PERCENT)
        .scalar()
    )

    failed = (
        session.query(func.count(Credential.id))
        .filter(
            Credential.delivery_status == DELIVERY_FAILED,
            Credential.issued_at >= now - timedelta(days=7),
        )
        .scalar()
    )

    return {
        "period": period,
        "active_orgs": int(active or 0),
        "credentials_issued": int(issued or 0),
        "near_limit_orgs": int(near or 0),
        "near_limit_percent": NEAR_LIMIT_PERCENT,
        # Credentials issued in the last 7 days whose email last failed. A
        # failed send records no timestamp of its own, so the window is on
        # issued_at — which is also when nearly every send happens.
        "failed_emails_7d": int(failed or 0),
    }


# -- data quality ------------------------------------------------------------------

#: A title that is an address: someone put the email in the title column.
_EMAIL_LIKE = re.compile(r"^\s*[^\s@]+@[^\s@]+\.[^\s@]+\s*$")


def title_looks_like_email(title: str) -> bool:
    return bool(_EMAIL_LIKE.match(title or ""))


@dataclass(frozen=True)
class CredentialKey:
    public_id: str
    org_id: object
    recipient_name: str
    recipient_email: str
    issued_at: datetime


def _as_aware(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; Postgres aware ones.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def possible_duplicates(
    rows: Iterable[CredentialKey],
    candidates: Iterable[CredentialKey],
    window: timedelta = DUPLICATE_WINDOW,
) -> set[str]:
    """Public ids in `rows` for which another credential in `candidates`, from
    the same org, went to the same recipient name or email (case- and
    space-insensitive) within `window` of it. A row never matches itself.
    An empty email matches nothing — "no address" is not an address."""
    by_org: dict[object, list[CredentialKey]] = {}
    for c in candidates:
        by_org.setdefault(c.org_id, []).append(c)

    flagged = set()
    for row in rows:
        name = name_key(row.recipient_name)
        email = name_key(row.recipient_email)
        at = _as_aware(row.issued_at)
        for other in by_org.get(row.org_id, ()):
            if other.public_id == row.public_id:
                continue
            same_person = (name and name == name_key(other.recipient_name)) or (
                email and email == name_key(other.recipient_email)
            )
            if same_person and abs(_as_aware(other.issued_at) - at) <= window:
                flagged.add(row.public_id)
                break
    return flagged


def duplicate_candidates(session, rows: list[Credential]) -> list[CredentialKey]:
    """Every credential that could make a row on this page a duplicate: same
    org, same name or email, issued within the window of the page's span.
    One query for the page."""
    if not rows:
        return []
    org_ids = {r.org_id for r in rows}
    names = {name_key(r.recipient_name) for r in rows if name_key(r.recipient_name)}
    emails = {name_key(r.recipient_email) for r in rows if name_key(r.recipient_email)}
    times = [_as_aware(r.issued_at) for r in rows]
    start, end = min(times) - DUPLICATE_WINDOW, max(times) + DUPLICATE_WINDOW

    person = []
    if names:
        person.append(func.lower(func.trim(Credential.recipient_name)).in_(sorted(names)))
    if emails:
        person.append(func.lower(func.trim(Credential.recipient_email)).in_(sorted(emails)))
    if not person:
        return []

    found = (
        session.query(
            Credential.public_id, Credential.org_id, Credential.recipient_name,
            Credential.recipient_email, Credential.issued_at,
        )
        .filter(
            Credential.org_id.in_(org_ids),
            or_(*person),
            Credential.issued_at >= start,
            Credential.issued_at <= end,
        )
        .all()
    )
    return [CredentialKey(*f) for f in found]


def as_key(c: Credential) -> CredentialKey:
    return CredentialKey(c.public_id, c.org_id, c.recipient_name, c.recipient_email or "", c.issued_at)


# -- resend ------------------------------------------------------------------------

def resend_refusal(
    cred: Credential, *, now: Optional[datetime] = None, session=None
) -> Optional[str]:
    """Why an operator may not resend this credential's email, or None if
    they may. The console's own rule, on top of `resend_credential()`'s:
    a failed send, or a pending/unknown one that has had an hour to land.
    A `sent` row is the org's call to resend, not an operator's."""
    now = now or datetime.now(timezone.utc)
    if cred.status == REVOKED:
        return "A revoked credential cannot be resent."
    if is_test_credential(cred):
        return "Test credentials never send email."
    if not (cred.recipient_email or "").strip():
        return "This credential has no recipient email."
    if (cred.delivery_attempts or 0) >= MAX_DELIVERY_ATTEMPTS:
        return f"This credential has already been emailed {MAX_DELIVERY_ATTEMPTS} times."
    # The org resend's own check, so the console never offers a button that
    # the send path would then refuse. The gate's memo means a page of 200
    # rows reads its table once, not 200 times.
    paused = email_paused_refusal(cred, session, now=now)
    if paused:
        return paused
    if cred.delivery_status == DELIVERY_FAILED:
        return None
    if cred.delivery_status in (DELIVERY_PENDING, DELIVERY_UNKNOWN):
        if now - _as_aware(cred.issued_at) >= RESEND_GRACE:
            return None
        return "This send is still in progress. Wait an hour before resending."
    return f"Only failed sends can be resent from here (this one is {cred.delivery_status})."


class ResendConflict(Exception):
    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.message = message
        self.error_type = error_type


def resend_credential_email(public_id: str, *, actor: str, idempotency_key: str) -> dict:
    """Resend one credential's email on an operator's behalf, exactly once per
    `idempotency_key`, and record it in `operator_actions`.

    Three transactions, deliberately:

    1. Claim: check the rule, then insert the `started` row and commit it.
       The unique key turns a repeated request into a replay; the partial
       unique index turns a concurrent one for the same credential into a
       409. Nothing has been sent yet, so a refusal here costs nothing.
    2. Send: `resend_credential()`, the org dashboard's own path — it
       re-checks revoked/test/address/attempts, increments
       `delivery_attempts` and records the outcome on the credential.
    3. Record: the outcome on the action row. If (2) raised, the row is
       still closed, so the in-flight lock cannot stick.

    Returns the response body, with `replayed: true` for a repeated key.
    """
    with get_db() as session:
        existing = session.query(OperatorAction).filter_by(idempotency_key=idempotency_key).first()
        if existing is not None:
            return _replay(existing, public_id)

        cred = session.query(Credential).filter_by(public_id=public_id).first()
        if cred is None:
            raise ResendConflict("Credential not found", "not_found")
        refusal = resend_refusal(cred, session=session)
        if refusal:
            raise ResendConflict(refusal, "resend_not_allowed")
        org = session.query(Organization).filter_by(id=cred.org_id).one()
        org_slug, org_id = org.slug, org.id

    try:
        with get_db() as session:
            session.add(OperatorAction(
                actor=actor, action=RESEND_ACTION, org_id=org_id, target=public_id,
                idempotency_key=idempotency_key, status=STARTED,
            ))
    except IntegrityError:
        with get_db() as session:
            existing = session.query(OperatorAction).filter_by(idempotency_key=idempotency_key).first()
            if existing is not None:
                return _replay(existing, public_id)
        raise ResendConflict(
            "Another resend of this credential is already in progress.", "resend_in_progress"
        )

    status, result, error = FAILED, None, None
    try:
        outcome = resend_credential(org_slug, public_id)
        result = {**outcome, "replayed": False}
        status = SUCCEEDED
        return result
    except IssuanceError as exc:
        status, error = REFUSED, exc.message
        raise ResendConflict(exc.message, "resend_not_allowed")
    except Exception as exc:  # noqa: BLE001 — recorded, then re-raised
        error = str(exc)[:1000]
        raise
    finally:
        with get_db() as session:
            row = session.query(OperatorAction).filter_by(idempotency_key=idempotency_key).one()
            row.status = status
            row.result = result
            row.error = error
            row.finished_at = datetime.now(timezone.utc)


def _replay(action: OperatorAction, public_id: str) -> dict:
    if action.target != public_id or action.action != RESEND_ACTION:
        raise ResendConflict(
            "This idempotency key was already used for a different request.", "idempotency_key_reused"
        )
    if action.status == STARTED:
        raise ResendConflict("This resend is still in progress.", "resend_in_progress")
    if action.status == SUCCEEDED and action.result:
        return {**action.result, "replayed": True}
    raise ResendConflict(action.error or "This resend did not complete.", "resend_not_allowed")
