"""
Comprehensive test suite for the PDF Cert Generator API.
Run with: python test_api.py
Requires: pip install requests
"""

import sys
import io
import requests

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_URL = "http://localhost:8000"
RESULTS: list[tuple[str, bool]] = []


def record(name: str, passed: bool):
    RESULTS.append((name, passed))
    mark = "\u2705" if passed else "\u274c"
    print(f"  {mark} {name}")


# ── Core API endpoints ────────────────────────────────────────────────

def test_health():
    r = requests.get(f"{BASE_URL}/api/health")
    data = r.json()
    record("GET /api/health returns 200", r.status_code == 200)
    record("Health version is 2.0.0", data.get("version") == "2.0.0")


def test_root():
    r = requests.get(f"{BASE_URL}/")
    data = r.json()
    record("GET / returns 200", r.status_code == 200)
    record("Root version is 2.0.0", data.get("version") == "2.0.0")


def test_info():
    r = requests.get(f"{BASE_URL}/api/info")
    data = r.json()
    record("GET /api/info returns 200", r.status_code == 200)
    record("Info version is 2.0.0", data.get("version") == "2.0.0")


# ── Courses ───────────────────────────────────────────────────────────

def test_courses():
    r = requests.get(f"{BASE_URL}/api/courses")
    data = r.json()
    courses = data.get("courses", [])
    record("GET /api/courses returns 200", r.status_code == 200)
    record("Courses list is non-empty", len(courses) > 0)
    record("AI Code Reviewer Course is present", "AI Code Reviewer Course" in courses)


# ── Certificate creation ─────────────────────────────────────────────

def _create_cert(**overrides) -> requests.Response:
    body = {
        "participant_name": "Test User",
        "course_name": "AI Code Reviewer Course",
        "completion_date": "2026-04-15",
        "instructor_name": "Certificate Team",
        **overrides,
    }
    return requests.post(f"{BASE_URL}/api/certificate", json=body)


def test_certificate_creation():
    r = _create_cert()
    data = r.json()
    record("POST /api/certificate returns 200", r.status_code == 200)
    record("Response has token", bool(data.get("token")))
    record("Response has url", bool(data.get("url")))
    record("Response has download_url", bool(data.get("download_url")))
    record("Response has certificate_id starting with CERT-", data.get("certificate_id", "").startswith("CERT-"))
    record("Participant name echoed back", data.get("participant_name") == "Test User")
    return data


def test_certificate_validation_bad_course():
    r = _create_cert(course_name="Nonexistent Course 999")
    record("Invalid course returns 400", r.status_code == 400)


def test_certificate_validation_empty_name():
    r = _create_cert(participant_name="   ")
    record("Empty name returns 400", r.status_code == 400)


def test_internship_certificate():
    """VTU-style internship payload: USN, duration, hours, mentor + verifiable token."""
    body = {
        "participant_name": "Internship API Test",
        "course_name": "AI Code Reviewer Course",
        "completion_date": "2026-06-10",
        "instructor_name": "Program Lead",
        "certificate_kind": "internship",
        "usn": "1RV22CS099",
        "internship_duration": "Jan 2026 – Jun 2026",
        "internship_hours": "120",
        "mentor_name": "Industry Mentor",
        "institution_name": "Sample Engineering College",
    }
    r = requests.post(f"{BASE_URL}/api/certificate", json=body)
    data = r.json()
    record("POST internship certificate returns 200", r.status_code == 200)
    record("Internship certificate_kind in response", data.get("certificate_kind") == "internship")
    record("Internship USN echoed", data.get("usn") == "1RV22CS099")
    token = data.get("token", "")
    if not token:
        record("Internship token present", False)
        return
    v = requests.get(f"{BASE_URL}/certificate/{token}/verify").json()
    record("Verify internship returns certificate_kind", v.get("certificate_kind") == "internship")
    record("Verify includes mentor_name", v.get("mentor_name") == "Industry Mentor")
    pdf = requests.get(data.get("download_url", ""))
    record("Internship PDF returns 200", pdf.status_code == 200)
    record("Internship PDF is non-empty", len(pdf.content) > 500)
    record("Internship PDF filename hint", "attachment" in pdf.headers.get("Content-Disposition", "").lower())


# ── Invoice generation ────────────────────────────────────────────────

def _create_invoice(**overrides) -> requests.Response:
    body = {
        "invoice_number": "INV-TEST-1",
        "invoice_date": "2026-07-09",
        "bill_from_name": "Naveen Katiyar",
        "bill_from_address": "68, Vijaynagar, Kanpur\nUttar Pradesh",
        "bill_from_pan": "XXXXXXX30A",
        "bill_to_name": "Cognyzer",
        "bill_to_address": "Building No.3, Sukan Mall, Ahmedabad",
        "bill_to_gstin": "24AAWFC3808N1ZX",
        "bill_to_email": "team@cognyzer.com",
        "exchange_rate": 90,
        "signature_name": "Naveen Katiyar",
        "line_items": [
            {
                "description": "Dataset preparation and validation services",
                "rate": 22,
                "rate_label": "$22 / Task",
                "quantity": 10,
                "quantity_label": "10 task",
            }
        ],
        **overrides,
    }
    return requests.post(f"{BASE_URL}/api/invoice", json=body)


def test_invoice_creation():
    r = _create_invoice()
    data = r.json()
    record("POST /api/invoice returns 200", r.status_code == 200)
    record("Invoice response has token", bool(data.get("token")))
    record("Invoice response has download_url", bool(data.get("download_url")))
    record("Invoice total INR is 19800", data.get("total_inr") == 19800)
    record("Invoice amount in words present", "Nineteen Thousand Eight Hundred Only" in data.get("amount_in_words", ""))
    pdf = requests.get(data.get("download_url", ""))
    record("Invoice PDF returns 200", pdf.status_code == 200)
    record("Invoice PDF is application/pdf", "application/pdf" in pdf.headers.get("Content-Type", ""))
    record("Invoice PDF is non-empty", len(pdf.content) > 500)


# ── Public viewer page ────────────────────────────────────────────────

def test_viewer_page(cert_data: dict):
    url = cert_data.get("url", "")
    if not url:
        record("Viewer page — skipped (no url)", False)
        return
    r = requests.get(url)
    record("GET certificate viewer returns 200", r.status_code == 200)
    record("Viewer is HTML", "text/html" in r.headers.get("Content-Type", ""))
    record("Viewer contains participant name", "Test User" in r.text)


# ── PDF download ──────────────────────────────────────────────────────

def test_pdf_download(cert_data: dict):
    url = cert_data.get("download_url", "")
    if not url:
        record("PDF download — skipped (no download_url)", False)
        return
    r = requests.get(url)
    record("GET certificate PDF returns 200", r.status_code == 200)
    record("PDF Content-Type is application/pdf", "application/pdf" in r.headers.get("Content-Type", ""))
    record("PDF body is non-empty", len(r.content) > 500)


# ── Verification API ─────────────────────────────────────────────────

def test_verify_valid(cert_data: dict):
    token = cert_data.get("token", "")
    r = requests.get(f"{BASE_URL}/certificate/{token}/verify")
    data = r.json()
    record("GET /certificate/{token}/verify returns 200", r.status_code == 200)
    record("Verify response has valid=True", data.get("valid") is True)
    record("Verify returns correct participant", data.get("participant_name") == "Test User")
    record("Verify returns correct course", data.get("course_name") == "AI Code Reviewer Course")
    record("Verify participation kind", data.get("certificate_kind") == "participation")


# ── Tamper detection ──────────────────────────────────────────────────

def test_tamper_detection(cert_data: dict):
    token = cert_data.get("token", "")
    if not token:
        record("Tamper detection — skipped (no token)", False)
        return

    tampered = token[:-4] + "ZZZZ"
    r = requests.get(f"{BASE_URL}/certificate/{tampered}/verify")
    record("Tampered token verify returns 400", r.status_code == 400)
    data = r.json()
    record("Tampered response has valid=False", data.get("valid") is False)

    r2 = requests.get(f"{BASE_URL}/certificate/{tampered}")
    record("Tampered token viewer returns 404", r2.status_code == 404)


# ── Rate limiting (basic) ────────────────────────────────────────────

def test_rate_limiting():
    """Fire many requests quickly; should eventually get 429 if rate limiter is active."""
    got_429 = False
    for _ in range(15):
        r = _create_cert()
        if r.status_code == 429:
            got_429 = True
            break
    record("Rate limiter triggers 429 within 15 requests", got_429)


# ── Runner ────────────────────────────────────────────────────────────

def run_all():
    print("=" * 60)
    print("  PDF Cert Generator API — Test Suite")
    print("=" * 60)

    print("\n[Core Endpoints]")
    test_health()
    test_root()
    test_info()

    print("\n[Courses]")
    test_courses()

    print("\n[Certificate Creation]")
    cert = test_certificate_creation()

    print("\n[Validation Errors]")
    test_certificate_validation_bad_course()
    test_certificate_validation_empty_name()

    print("\n[Internship / VTU certificate]")
    test_internship_certificate()

    print("\n[Invoice generation]")
    test_invoice_creation()

    print("\n[Public Viewer]")
    test_viewer_page(cert)

    print("\n[PDF Download]")
    test_pdf_download(cert)

    print("\n[Verification API]")
    test_verify_valid(cert)

    print("\n[Tamper Detection]")
    test_tamper_detection(cert)

    print("\n[Rate Limiting]")
    test_rate_limiting()

    # Summary
    total = len(RESULTS)
    passed = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed == total:
        print("\n\u2705 All tests passed!")
    else:
        failed = [(n, ok) for n, ok in RESULTS if not ok]
        print(f"\n\u274c {len(failed)} test(s) failed:")
        for name, _ in failed:
            print(f"   - {name}")
    return passed == total


if __name__ == "__main__":
    try:
        success = run_all()
        sys.exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print("\n\u274c Could not connect to the API at", BASE_URL)
        print("   Start the server first:")
        print("   python -m uvicorn api.index:app --reload --port 8000")
        sys.exit(1)
    except Exception as e:
        print(f"\n\u274c Unexpected error: {e}")
        sys.exit(1)
