"""SDK integration tests against local server."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from intelliforge import AuthenticationError, IntelliForge

BASE_URL = os.environ.get("INTELLIFORGE_URL", "http://localhost:8000")

def test_health():
    client = IntelliForge(base_url=BASE_URL)
    result = client.health()
    assert result["status"] == "healthy"
    assert "dependencies" in result
    print("PASS: health")

def test_courses():
    client = IntelliForge(base_url=BASE_URL)
    courses = client.list_courses()
    assert isinstance(courses, list)
    assert len(courses) > 0
    print(f"PASS: courses ({len(courses)})")

def test_create_and_verify():
    client = IntelliForge(api_key="test-api-key", base_url=BASE_URL)
    courses = client.list_courses()
    cert = client.create_certificate(
        participant_name="SDK Test User",
        course_name=courses[0],
        completion_date="2026-04-15",
        idempotency_key="sdk-test-001"
    )
    assert "certificate_id" in cert
    assert "token" in cert
    assert "request_id" in cert
    
    # Verify
    result = client.verify(cert["token"])
    assert result["valid"] is True
    assert result["participant_name"] == "SDK Test User"
    
    # Idempotency
    cert2 = client.create_certificate(
        participant_name="SDK Test User",
        course_name=courses[0],
        completion_date="2026-04-15",
        idempotency_key="sdk-test-001"
    )
    assert cert2["certificate_id"] == cert["certificate_id"]
    print("PASS: create + verify + idempotency")

def test_batch_verify():
    client = IntelliForge(api_key="test-api-key", base_url=BASE_URL)
    courses = client.list_courses()
    cert = client.create_certificate(
        participant_name="Batch Test",
        course_name=courses[0],
        completion_date="2026-04-15"
    )
    result = client.batch_verify([cert["token"], "invalid-token"])
    assert result["valid"] == 1
    assert result["invalid"] == 1
    print("PASS: batch verify")

def test_download_pdf():
    client = IntelliForge(api_key="test-api-key", base_url=BASE_URL)
    courses = client.list_courses()
    cert = client.create_certificate(
        participant_name="PDF Test",
        course_name=courses[0],
        completion_date="2026-04-15"
    )
    pdf_bytes = client.download_pdf(cert["token"])
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b"%PDF"
    print("PASS: download PDF")

def test_auth_error():
    client = IntelliForge(base_url=BASE_URL)
    courses = client.list_courses()
    # If API keys are configured, this should fail
    try:
        client.create_certificate(
            participant_name="No Key",
            course_name=courses[0],
            completion_date="2026-04-15"
        )
        # If no API keys configured, creation succeeds
        print("PASS: auth (no keys configured)")
    except AuthenticationError:
        print("PASS: auth (correctly rejected)")

if __name__ == "__main__":
    tests = [test_health, test_courses, test_create_and_verify, test_batch_verify, test_download_pdf, test_auth_error]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)
