import pytest
from fastapi.testclient import TestClient

def test_create_org(client: TestClient, mock_clerk):
    payload = {
        "clerk_org_id": "org_123",
        "slug": "test-org",
        "name": "Test Organization",
        "logo_url": "https://example.com/logo.png"
    }
    response = client.post("/api/v1/orgs", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["slug"] == "test-org"
    assert data["data"]["name"] == "Test Organization"

def test_create_org_duplicate_slug(client: TestClient, mock_clerk):
    payload = {
        "clerk_org_id": "org_456",
        "slug": "duplicate-org",
        "name": "First Org"
    }
    client.post("/api/v1/orgs", json=payload)
    
    # Try to create with same slug
    payload2 = {
        "clerk_org_id": "org_789",
        "slug": "duplicate-org",
        "name": "Second Org"
    }
    response = client.post("/api/v1/orgs", json=payload2)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == 409

def test_get_org(client: TestClient, mock_clerk):
    # Create org first
    payload = {
        "clerk_org_id": "org_abc",
        "slug": "fetchable-org",
        "name": "Fetchable Org"
    }
    client.post("/api/v1/orgs", json=payload)
    
    # Fetch org
    response = client.get("/api/v1/orgs/fetchable-org")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["slug"] == "fetchable-org"

def test_update_org(client: TestClient, mock_clerk):
    # Create org
    payload = {
        "clerk_org_id": "org_upd",
        "slug": "updatable-org",
        "name": "Old Name"
    }
    client.post("/api/v1/orgs", json=payload)
    
    # Update org
    update_payload = {"name": "New Name"}
    response = client.patch("/api/v1/orgs/updatable-org", json=update_payload)
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "New Name"

def test_list_org_members(client: TestClient, mock_clerk):
    # Create org
    payload = {
        "clerk_org_id": "org_mem",
        "slug": "members-org",
        "name": "Members Org"
    }
    client.post("/api/v1/orgs", json=payload)
    
    # List members
    response = client.get("/api/v1/orgs/members-org/members")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1 # The creator should be owner
    assert data["data"][0]["role"] == "owner"
    assert data["data"][0]["clerk_user_id"] == "test_user_123"
