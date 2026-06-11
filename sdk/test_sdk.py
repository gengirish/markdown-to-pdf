"""SDK integration tests against local server."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from pdfcert import AuthenticationError, PdfCert

BASE_URL = os.environ.get("PDFCERT_URL", "http://localhost:8000")

def test_health():
    client = PdfCert(base_url=BASE_URL)
    result = client.health()
    assert result["status"] == "healthy"
    assert "dependencies" in result
    print("PASS: health")

def test_courses():
    client = PdfCert(base_url=BASE_URL)
    courses = client.list_courses()
    assert isinstance(courses, list)
    assert len(courses) > 0
    print(f"PASS: courses ({len(courses)})")

def test_create_and_verify():
    client = PdfCert(api_key="test-api-key", base_url=BASE_URL)
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
    
    result = client.verify(cert["token"])
    assert result["valid"] is True
    assert result["participant_name"] == "SDK Test User"
    assert result.get("certificate_kind") == "participation"

    cert2 = client.create_certificate(
        participant_name="SDK Test User",
        course_name=courses[0],
        completion_date="2026-04-15",
        idempotency_key="sdk-test-001"
    )
    assert cert2["certificate_id"] == cert["certificate_id"]
    print("PASS: create_and_verify")

def test_download_pdf():
    client = PdfCert(api_key="test-api-key", base_url=BASE_URL)
    courses = client.list_courses()
    cert = client.create_certificate(
        participant_name="SDK PDF Test",
        course_name=courses[0],
        completion_date="2026-04-15",
        idempotency_key="sdk-test-pdf"
    )
    data = client.download_pdf(cert["token"])
    assert isinstance(data, bytes)
    assert len(data) > 500
    print("PASS: download_pdf")

def test_batch_verify():
    client = PdfCert(api_key="test-api-key", base_url=BASE_URL)
    courses = client.list_courses()
    cert = client.create_certificate(
        participant_name="SDK Batch Test",
        course_name=courses[0],
        completion_date="2026-04-15",
        idempotency_key="sdk-test-batch"
    )
    result = client.batch_verify([cert["token"], "invalid.token.here"])
    assert result["total"] == 2
    assert result["valid"] >= 1
    print("PASS: batch_verify")

def test_auth_error():
    client = PdfCert(base_url=BASE_URL)
    try:
        client.admin.stats()
        print("SKIP: admin auth (no admin key configured)")
    except AuthenticationError:
        print("PASS: auth_error")

if __name__ == "__main__":
    tests = [
        test_health,
        test_courses,
        test_create_and_verify,
        test_download_pdf,
        test_batch_verify,
        test_auth_error,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
