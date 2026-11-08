"""The operator console: KPIs, the sortable org list, deliveries counts,
filters and export, data-quality flags, and the operator resend.

The test DB is shared across the session, so anything counting across every
org (KPIs) asserts a delta, never an absolute.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute

from api.core import config
from api.core.config import BILLING_TIERS, TIER_ALIASES
from api.index import app
from api.models.credential import Credential
from api.models.operator_action import OperatorAction, STARTED
from api.models.organization import Organization
from api.models.usage import UsageLedger
from api.services.issuance import effective_credential_quota
from api.services.operator_console import (
    CredentialKey,
    effective_limit_sql,
    possible_duplicates,
    title_looks_like_email,
    usage_percent,
)

OPERATOR = "test_user_123"
SEND = "api.services.delivery.agentmail_deliver"
NOW = datetime.now(timezone.utc)


@pytest.fixture
def operator(monkeypatch, mock_clerk):
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset({OPERATOR}))


def make_org(db, slug, *, tier="community", override=None, used=None, name=None):
    org = Organization(slug=slug, name=name or slug.title(), tier=tier, credential_quota_override=override)
    db.add(org)
    db.commit()
    if used is not None:
        db.add(UsageLedger(org_id=org.id, period=UsageLedger.current_period(), credentials_issued=used))
        db.commit()
    return org


def make_cred(db, org, public_id, *, email="a@example.com", name=None, status="failed",
              issued_at=None, title="Course", attempts=1, metadata=None, cred_status="issued"):
    cred = Credential(
        public_id=public_id, org_id=org.id, recipient_name=name or public_id.title(),
        recipient_email=email, title=title, metadata_=metadata or {}, hmac_signature="x",
        status=cred_status, delivery_status=status, delivery_attempts=attempts,
        issued_at=issued_at or NOW,
    )
    db.add(cred)
    db.commit()
    return cred


# -- the enforced limit: SQL and Python must agree -------------------------------

def _cases():
    tiers = list(BILLING_TIERS) + list(TIER_ALIASES) + ["enterprise-unknown"]
    for tier in tiers:
        for override in (None, -1, 0, 777):
            yield tier, override


def test_effective_limit_sql_matches_effective_credential_quota(db_session):
    """`effective_limit_sql()` is a second implementation of the rule issuance
    enforces. Every tier, alias, an unknown tier, and each kind of override."""
    for i, (tier, override) in enumerate(_cases()):
        org = make_org(db_session, f"opc-parity-{i}", tier=tier, override=override)
        in_sql = (
            db_session.query(effective_limit_sql()).filter(Organization.id == org.id).scalar()
        )
        assert in_sql == effective_credential_quota(org), (tier, override)


def test_usage_percent():
    assert usage_percent(40, 50) == 80.0
    assert usage_percent(5, None) is None
    assert usage_percent(5, -1) is None
    # An override of 0 stops an org: it is at its limit, not at 0%.
    assert usage_percent(0, 0) == 100.0
    assert usage_percent(60, 50) == 120.0


# -- the org list ----------------------------------------------------------------

def _orgs(client, **params):
    r = client.get("/api/v1/operator/orgs", params={"q": "opc-list-", **params})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_org_list_sorts_by_usage_and_filters(client, operator, db_session):
    make_org(db_session, "opc-list-busy", used=45)            # 90% of 50
    make_org(db_session, "opc-list-half", used=25)            # 50%
    make_org(db_session, "opc-list-idle")                     # 0%
    make_org(db_session, "opc-list-scale", tier="scale", used=900)  # unlimited
    make_org(db_session, "opc-list-over", override=10, used=12)     # 120%

    data = _orgs(client)
    slugs = [o["slug"] for o in data["orgs"]]
    # Busiest first; unlimited orgs have no percentage and sort last.
    assert slugs == ["opc-list-over", "opc-list-busy", "opc-list-half", "opc-list-idle", "opc-list-scale"]
    by_slug = {o["slug"]: o for o in data["orgs"]}
    assert by_slug["opc-list-busy"]["usage_percent"] == 90.0
    assert by_slug["opc-list-scale"]["usage_percent"] is None

    assert {o["slug"] for o in _orgs(client, near_limit=True)["orgs"]} == {"opc-list-over", "opc-list-busy"}
    assert "opc-list-idle" not in {o["slug"] for o in _orgs(client, active=True)["orgs"]}
    assert [o["slug"] for o in _orgs(client, has_override=True)["orgs"]] == ["opc-list-over"]
    assert [o["slug"] for o in _orgs(client, tier=["scale"])["orgs"]] == ["opc-list-scale"]

    by_used = [o["slug"] for o in _orgs(client, sort="used", dir="desc")["orgs"]]
    assert by_used[0] == "opc-list-scale"


def test_org_list_tier_filter_includes_retired_aliases(client, operator, db_session):
    make_org(db_session, "opc-list-alias", tier="starter")
    assert "opc-list-alias" in {o["slug"] for o in _orgs(client, tier=["pro"])["orgs"]}


def test_org_list_reports_last_activity_and_shared_names(client, operator, db_session):
    a = make_org(db_session, "opc-list-dup-a", name="Acme Academy")
    make_org(db_session, "opc-list-dup-b", name="  acme academy ")
    make_org(db_session, "opc-list-unique", name="Unique Name Org")
    when = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    make_cred(db_session, a, "OPC-LAST-1", issued_at=when - timedelta(days=3))
    make_cred(db_session, a, "OPC-LAST-2", issued_at=when)

    rows = {o["slug"]: o for o in _orgs(client)["orgs"]}
    assert rows["opc-list-dup-a"]["duplicate_name"] is True
    assert rows["opc-list-dup-b"]["duplicate_name"] is True
    assert rows["opc-list-unique"]["duplicate_name"] is False
    assert datetime.fromisoformat(rows["opc-list-dup-a"]["last_activity_at"]) == when
    assert rows["opc-list-unique"]["last_activity_at"] is None


def test_org_detail_carries_drawer_facts(client, operator, db_session):
    org = make_org(db_session, "opc-detail", used=10)
    make_cred(db_session, org, "OPC-DETAIL-1")
    make_cred(db_session, org, "OPC-DETAIL-2")
    data = client.get("/api/v1/operator/orgs/opc-detail/credential-quota").json()["data"]
    assert data["credentials_all_time"] == 2
    assert data["member_count"] == 0
    assert data["usage_percent"] == 20.0
    assert data["created_at"] and data["last_activity_at"]


# -- KPIs ----------------------------------------------------------------------------

def _kpis(client):
    r = client.get("/api/v1/operator/kpis")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_kpis_count_this_month_and_the_last_seven_days(client, operator, db_session):
    before = _kpis(client)

    make_org(db_session, "opc-kpi-active", used=10)        # active, 20%
    make_org(db_session, "opc-kpi-near", used=41)          # active, 82%
    make_org(db_session, "opc-kpi-zero", used=0)           # a ledger row, but not active
    mail = make_org(db_session, "opc-kpi-mail")
    make_cred(db_session, mail, "OPC-KPI-F1", status="failed")
    make_cred(db_session, mail, "OPC-KPI-F2", status="failed", issued_at=NOW - timedelta(days=9))
    make_cred(db_session, mail, "OPC-KPI-S1", status="sent")

    after = _kpis(client)
    assert after["active_orgs"] - before["active_orgs"] == 2
    assert after["credentials_issued"] - before["credentials_issued"] == 51
    assert after["near_limit_orgs"] - before["near_limit_orgs"] == 1
    assert after["failed_emails_7d"] - before["failed_emails_7d"] == 1


# -- deliveries ------------------------------------------------------------------------

def _deliveries(client, **params):
    r = client.get("/api/v1/operator/deliveries", params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_deliveries_count_each_status_under_the_other_filters(client, operator, db_session):
    org = make_org(db_session, "opc-mail-counts")
    make_cred(db_session, org, "OPC-C-1", status="failed")
    make_cred(db_session, org, "OPC-C-2", status="failed")
    make_cred(db_session, org, "OPC-C-3", status="sent")
    make_cred(db_session, org, "OPC-C-4", status="not_requested", email="")

    data = _deliveries(client, org="opc-mail-counts", delivery_status="failed")
    assert data["total"] == 2
    # Counts ignore the status filter itself, so every option can show its number.
    assert data["counts"]["failed"] == 2
    assert data["counts"]["sent"] == 1
    assert data["counts"]["attempted"] == 3
    assert data["counts"]["all"] == 4


def test_deliveries_filter_by_date_range(client, operator, db_session):
    org = make_org(db_session, "opc-mail-dates")
    make_cred(db_session, org, "OPC-D-NEW", status="sent", issued_at=NOW - timedelta(hours=2))
    make_cred(db_session, org, "OPC-D-OLD", status="sent", issued_at=NOW - timedelta(days=20))

    since = (NOW - timedelta(days=1)).isoformat()
    assert [d["id"] for d in _deliveries(client, org="opc-mail-dates", since=since)["deliveries"]] == ["OPC-D-NEW"]
    until = (NOW - timedelta(days=7)).isoformat()
    assert [d["id"] for d in _deliveries(client, org="opc-mail-dates", until=until)["deliveries"]] == ["OPC-D-OLD"]

    r = client.get("/api/v1/operator/deliveries", params={"since": NOW.isoformat(), "until": since})
    assert r.status_code == 422


def test_deliveries_sort_and_page_by_offset(client, operator, db_session):
    org = make_org(db_session, "opc-mail-sort")
    for i, attempts in enumerate([2, 0, 3, 1]):
        make_cred(db_session, org, f"OPC-S-{i}", status="sent", attempts=attempts)

    first = _deliveries(client, org="opc-mail-sort", sort="attempts", dir="desc", limit=2)
    second = _deliveries(client, org="opc-mail-sort", sort="attempts", dir="desc", limit=2, offset=2)
    assert [d["delivery_attempts"] for d in first["deliveries"] + second["deliveries"]] == [3, 2, 1, 0]
    assert first["total"] == 4


def test_deliveries_flag_data_quality(client, operator, db_session):
    org = make_org(db_session, "opc-mail-dq")
    other = make_org(db_session, "opc-mail-dq-other")
    make_cred(db_session, org, "OPC-Q-1", name="Ravi Kumar", email="ravi@example.com", title="ravi@example.com")
    make_cred(db_session, org, "OPC-Q-2", name="ravi kumar ", email="other@example.com",
              issued_at=NOW - timedelta(days=3))
    make_cred(db_session, other, "OPC-Q-3", name="Ravi Kumar", email="ravi@example.com")
    make_cred(db_session, org, "OPC-Q-4", name="Someone Else", email="else@example.com",
              issued_at=NOW - timedelta(days=30))

    rows = {}
    for slug in ("opc-mail-dq", "opc-mail-dq-other"):
        rows.update({d["id"]: d for d in _deliveries(client, org=slug, delivery_status="all")["deliveries"]})

    assert rows["OPC-Q-1"]["title_looks_like_email"] is True
    assert rows["OPC-Q-2"]["title_looks_like_email"] is False
    assert rows["OPC-Q-1"]["possible_duplicate"] is True    # same name, same org, 3 days apart
    assert rows["OPC-Q-2"]["possible_duplicate"] is True
    assert rows["OPC-Q-3"]["possible_duplicate"] is False   # same person, different org
    assert rows["OPC-Q-4"]["possible_duplicate"] is False


# -- the pure rules --------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("ada@example.com", True),
    ("  ada.l@uni.ac.in ", True),
    ("Python for Data Science", False),
    ("Workshop @ IIT Bombay", False),
    ("a@b", False),
    ("", False),
])
def test_title_looks_like_email(title, expected):
    assert title_looks_like_email(title) is expected


def _key(pid, org, name, email, days):
    return CredentialKey(pid, org, name, email, NOW - timedelta(days=days))


def test_possible_duplicates_rule():
    rows = [
        _key("A", 1, "Ada Lovelace", "ada@x.com", 0),
        _key("B", 1, "Grace Hopper", "", 0),
        _key("C", 1, "Alan Turing", "alan@x.com", 0),
        _key("D", 1, "Edsger", "", 0),
    ]
    candidates = rows + [
        _key("A2", 1, "ADA LOVELACE ", "different@x.com", 6),   # same name, 6 days
        _key("B2", 2, "Grace Hopper", "", 1),                    # different org
        _key("C2", 1, "Someone", "ALAN@x.com", 8),               # same email, 8 days: outside
        _key("D2", 1, "Other", "", 1),                           # both emails empty: no match
    ]
    assert possible_duplicates(rows, candidates) == {"A"}


def test_a_row_is_not_its_own_duplicate():
    row = _key("A", 1, "Ada", "ada@x.com", 0)
    assert possible_duplicates([row], [row]) == set()


# -- export ----------------------------------------------------------------------------

def test_export_is_the_filtered_view_as_csv(client, operator, db_session):
    org = make_org(db_session, "opc-export")
    make_cred(db_session, org, "OPC-E-1", status="failed", name="=HYPERLINK(\"http://evil\")")
    make_cred(db_session, org, "OPC-E-2", status="sent")

    r = client.get("/api/v1/operator/deliveries/export", params={"org": "opc-export", "delivery_status": "failed"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-export-truncated"] == "false"
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [row["Credential"] for row in rows] == ["OPC-E-1"]
    # A formula in customer input is defused, not executed by the spreadsheet.
    assert rows[0]["Recipient"].startswith("'=")


# -- resend ------------------------------------------------------------------------------

def _resend(client, public_id, key):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"/api/v1/operator/deliveries/{public_id}/resend", headers=headers)


def _actions(db, public_id):
    db.expire_all()
    return db.query(OperatorAction).filter_by(target=public_id).all()


def test_resend_is_idempotent_and_audited(client, operator, db_session):
    org = make_org(db_session, "opc-resend")
    make_cred(db_session, org, "OPC-R-1", status="failed", attempts=1)

    with patch(SEND, return_value=(True, "ok")) as send:
        first = _resend(client, "OPC-R-1", "key-double-click-1")
        second = _resend(client, "OPC-R-1", "key-double-click-1")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert send.call_count == 1  # a double-click sends once
    assert first.json()["data"]["replayed"] is False
    assert second.json()["data"]["replayed"] is True
    assert first.json()["data"]["sent"] is True

    db_session.expire_all()
    cred = db_session.query(Credential).filter_by(public_id="OPC-R-1").one()
    assert cred.delivery_attempts == 2
    assert cred.delivery_status == "sent"

    (action,) = _actions(db_session, "OPC-R-1")
    assert (action.actor, action.action, action.status) == (OPERATOR, "resend_credential_email", "succeeded")
    assert action.org_id == org.id
    assert action.finished_at is not None


def test_a_new_key_after_success_does_not_resend_a_sent_row(client, operator, db_session):
    org = make_org(db_session, "opc-resend-again")
    make_cred(db_session, org, "OPC-R-2", status="failed")
    with patch(SEND, return_value=(True, "ok")) as send:
        assert _resend(client, "OPC-R-2", "key-first-confirm").status_code == 200
        again = _resend(client, "OPC-R-2", "key-second-confirm")
    assert again.status_code == 409
    assert again.json()["error"]["type"] == "resend_not_allowed"
    assert send.call_count == 1


def test_a_concurrent_resend_of_the_same_credential_is_refused(client, operator, db_session):
    org = make_org(db_session, "opc-resend-inflight")
    make_cred(db_session, org, "OPC-R-3", status="failed")
    db_session.add(OperatorAction(
        actor="user_other_operator", action="resend_credential_email", org_id=org.id,
        target="OPC-R-3", idempotency_key="key-from-another-tab", status=STARTED,
    ))
    db_session.commit()
    with patch(SEND, return_value=(True, "ok")) as send:
        r = _resend(client, "OPC-R-3", "key-this-tab-0001")
    assert r.status_code == 409
    assert r.json()["error"]["type"] == "resend_in_progress"
    assert send.call_count == 0


def test_a_failed_resend_is_recorded_and_frees_the_lock(client, operator, db_session):
    org = make_org(db_session, "opc-resend-fail")
    make_cred(db_session, org, "OPC-R-4", status="failed", attempts=1)
    with patch(SEND, return_value=(False, "bounced")):
        r = _resend(client, "OPC-R-4", "key-fails-00001")
    assert r.status_code == 200
    assert r.json()["data"]["sent"] is False
    (action,) = _actions(db_session, "OPC-R-4")
    assert action.status == "succeeded"  # the action ran; the result says the send failed
    assert action.result["sent"] is False
    # The lock is released: another confirmation may try again.
    with patch(SEND, return_value=(True, "ok")):
        assert _resend(client, "OPC-R-4", "key-retry-00002").status_code == 200


@pytest.mark.parametrize("status,age,allowed", [
    ("failed", timedelta(0), True),
    ("pending", timedelta(minutes=30), False),
    ("pending", timedelta(hours=2), True),
    ("unknown", timedelta(hours=2), True),
    ("sent", timedelta(days=2), False),
    ("not_requested", timedelta(days=2), False),
])
def test_resend_eligibility(client, operator, db_session, status, age, allowed):
    slug = f"opc-elig-{status}-{int(age.total_seconds())}"
    org = make_org(db_session, slug)
    pid = slug.upper()
    make_cred(db_session, org, pid, status=status, issued_at=NOW - age)

    listed = _deliveries(client, org=slug, delivery_status="all")["deliveries"][0]
    assert listed["resendable"] is allowed
    # A refused row says why, so the console can explain a missing button.
    assert (listed["resend_refusal"] is None) is allowed
    with patch(SEND, return_value=(True, "ok")) as send:
        r = _resend(client, pid, f"key-{slug}")
    assert (r.status_code == 200) is allowed, r.text
    assert send.call_count == (1 if allowed else 0)


@pytest.mark.parametrize("kwargs,why", [
    ({"cred_status": "revoked"}, "revoked"),
    ({"metadata": {"_test": True}}, "Test"),
    ({"email": ""}, "no recipient"),
    ({"attempts": 3}, "3 times"),
])
def test_resend_refuses_what_the_org_resend_refuses(client, operator, db_session, kwargs, why):
    slug = f"opc-refuse-{why.split()[0].lower()}"
    org = make_org(db_session, slug)
    make_cred(db_session, org, slug.upper(), status="failed", **kwargs)
    with patch(SEND, return_value=(True, "ok")) as send:
        r = _resend(client, slug.upper(), f"key-{slug}")
    assert r.status_code == 409
    assert why in r.json()["error"]["message"]
    assert send.call_count == 0


def test_resend_requires_an_idempotency_key(client, operator, db_session):
    org = make_org(db_session, "opc-resend-nokey")
    make_cred(db_session, org, "OPC-R-NOKEY", status="failed")
    assert _resend(client, "OPC-R-NOKEY", None).status_code == 422


def test_resend_of_a_missing_credential_is_404(client, operator):
    assert _resend(client, "OPC-NOPE", "key-missing-0001").status_code == 404


# -- every operator route refuses a non-operator ----------------------------------------

def _operator_routes():
    """Read off the app, so a route added tomorrow is covered the day it lands."""
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/operator"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


OPERATOR_ROUTES = sorted(set(_operator_routes()))


def test_the_route_list_is_not_empty():
    paths = {path for _, path in OPERATOR_ROUTES}
    for expected in ("/api/v1/operator/kpis", "/api/v1/operator/deliveries/export",
                     "/api/v1/operator/deliveries/{public_id}/resend", "/api/v1/operator/tiers"):
        assert expected in paths


@pytest.mark.parametrize("method,path", OPERATOR_ROUTES)
def test_every_operator_route_is_403_for_a_non_operator(client, mock_clerk, monkeypatch, method, path):
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset({"user_someone_else"}))
    url = path.replace("{slug}", "any-org").replace("{public_id}", "CF-ANY")
    body = {"reason": "a reason long enough", "limit": 5, "tier": "pro"}
    with patch(SEND, return_value=(True, "ok")) as send:
        r = client.request(method, url, json=body, headers={"Idempotency-Key": "key-non-operator"})
    assert r.status_code == 403, (method, path, r.status_code)
    assert send.call_count == 0
