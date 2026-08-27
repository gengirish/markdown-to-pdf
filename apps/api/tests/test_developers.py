import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models.organization import Organization, OrgMember

def _create_org(db_session: Session, slug: str) -> dict:
    """Create an org owned by the user that the `mock_clerk` fixture returns.

    The OrgMember row is not optional: require_org_role resolves membership
    against the database, so an org with no members rejects every write.
    """
    org_id = uuid.uuid4()
    db_session.add(Organization(id=org_id, name="Test Org", slug=slug))
    db_session.add(OrgMember(org_id=org_id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()
    return {"id": str(org_id), "slug": slug}

def test_generate_api_key(client: TestClient, mock_clerk, db_session):
    """Test generating a new API key."""
    org = _create_org(db_session, "dev-keys-org")
    response = client.post(
        f"/api/v1/orgs/{org['slug']}/api-keys",
        json={"label": "Production Key"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "raw_key" in data
    assert data["raw_key"].startswith("cf_live_")
    assert data["kind"] == "live"
    assert data["label"] == "Production Key"
    
def test_list_and_revoke_api_keys(client: TestClient, mock_clerk, db_session):
    """Test listing and revoking an API key."""
    org = _create_org(db_session, "dev-list-org")
    
    # Create key
    res = client.post(f"/api/v1/orgs/{org['slug']}/api-keys", json={"label": "Test List Key"})
    key_id = res.json()["data"]["id"]
    
    # List keys
    list_res = client.get(f"/api/v1/orgs/{org['slug']}/api-keys")
    assert list_res.status_code == 200
    keys = list_res.json()["data"]
    assert any(k["id"] == key_id for k in keys)
    # Ensure raw_key is NOT returned in lists
    assert "raw_key" not in keys[0]
    
    # Revoke key
    rev_res = client.delete(f"/api/v1/orgs/{org['slug']}/api-keys/{key_id}")
    assert rev_res.status_code == 200
    
    # Ensure it's removed from the active list
    list_res2 = client.get(f"/api/v1/orgs/{org['slug']}/api-keys")
    keys2 = list_res2.json()["data"]
    assert not any(k["id"] == key_id for k in keys2)

def test_create_and_list_webhooks(client: TestClient, mock_clerk, db_session):
    """Test creating and listing webhooks."""
    org = _create_org(db_session, "dev-hooks-org")
    
    res = client.post(
        f"/api/v1/orgs/{org['slug']}/webhooks",
        json={"url": "https://example.com/webhook", "events": ["batch.completed"]}
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["url"] == "https://example.com/webhook"
    assert "secret" in data
    assert data["secret"].startswith("whsec_")
    
    # List
    list_res = client.get(f"/api/v1/orgs/{org['slug']}/webhooks")
    assert list_res.status_code == 200
    webhooks = list_res.json()["data"]
    assert len(webhooks) >= 1
    
    # Delete
    del_res = client.delete(f"/api/v1/orgs/{org['slug']}/webhooks/{data['id']}")
    assert del_res.status_code == 200
