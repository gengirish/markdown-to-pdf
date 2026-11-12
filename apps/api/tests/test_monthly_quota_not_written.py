"""W4a: nothing writes `organizations.monthly_quota` any more.

`services/plans.py` used to set it equal to the effective limit on every
tier and override change, so a rollback to code that read it would find a
current number. W4a stops that write; W4b drops the column. These guards
start each org at a sentinel no tier or override produces, then make the
change and assert the sentinel survived — a write of any effective limit,
which is what the old code did, cannot leave it in place.
"""

from api.models.organization import Organization
from api.services.issuance import effective_credential_quota
from api.services.plans import change_tier, set_credential_quota_override

#: Not any tier's quota and not an override the tests set, so a write of the
#: effective limit always changes it.
SENTINEL = 7

REASON = "W4a guard: monthly_quota must not move"


def _org(db_session, slug, **kwargs):
    org = Organization(slug=slug, name=slug.title(), monthly_quota=SENTINEL, **kwargs)
    db_session.add(org)
    db_session.commit()
    return org


def _reload(db_session, slug):
    db_session.expire_all()
    return db_session.query(Organization).filter_by(slug=slug).one()


def test_a_plan_change_does_not_write_monthly_quota(db_session):
    org = _org(db_session, "w4a-tier", tier="community", credential_quota_override=300)

    assert change_tier(db_session, org, "pro", actor="test", reason=REASON) is True
    db_session.commit()

    org = _reload(db_session, "w4a-tier")
    assert org.tier == "pro"
    assert org.credential_quota_override is None  # the change really happened
    assert effective_credential_quota(org) != SENTINEL
    assert org.monthly_quota == SENTINEL


def test_setting_and_removing_an_override_does_not_write_monthly_quota(db_session):
    org = _org(db_session, "w4a-override", tier="community")

    assert set_credential_quota_override(db_session, org, 250, actor="test", reason=REASON)
    db_session.commit()
    org = _reload(db_session, "w4a-override")
    assert effective_credential_quota(org) == 250
    assert org.monthly_quota == SENTINEL

    assert set_credential_quota_override(db_session, org, None, actor="test", reason=REASON)
    db_session.commit()
    org = _reload(db_session, "w4a-override")
    assert org.credential_quota_override is None
    assert org.monthly_quota == SENTINEL
