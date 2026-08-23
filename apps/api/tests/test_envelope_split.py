"""Regressions for the origin, error-envelope, and URL-resolution fixes.

The legacy surface and the /api/v1 surface share one FastAPI app and one
exception handler, and for a while they also shared one error body. These tests
hold the two apart: the legacy shape is frozen because sdk/pdfcert and the live
SPA parse it, and the v1 shape has to match what the routes' response_model
advertises.
"""

from api.core.config import CERTFORGE_WEB_URL


# ── The frozen legacy error body ──────────────────────────────────────────


def test_legacy_error_body_is_not_wrapped_in_the_v1_envelope(client):
    """The whole dict, not one key.

    Asserting the exact body is the point: it is what stops a future change to
    the v1 envelope from leaking into a surface with certificates already
    printed against it.
    """
    response = client.get("/certificate/bogus")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": 404,
            "message": "Invalid or tampered certificate",
            "type": "not_found",
        }
    }


def test_legacy_invoice_error_body_stays_bare(client):
    response = client.get("/invoice/bogus/download")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": 404,
            "message": "Invoice not found or invalid token",
            "type": "not_found",
        }
    }


# ── The v1 envelope ───────────────────────────────────────────────────────


def test_v1_error_body_carries_the_api_response_envelope(client):
    """v1 routes declare ApiResponse as their response_model.

    The global handler used to emit the bare legacy body for these too, so any
    failure returned a shape the OpenAPI schema never advertised.
    """
    response = client.get("/api/v1/orgs/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "data" in body
    assert body["data"] is None
    assert body["error"]["code"] == 404
    assert body["error"]["type"] == "not_found"
    assert body["error"]["message"] == "Organization not found"


# ── CORS ──────────────────────────────────────────────────────────────────


def _preflight(client, origin: str):
    return client.options(
        "/api/certificate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )


def test_preflight_allows_the_certforge_dashboard_origin(client):
    response = _preflight(client, CERTFORGE_WEB_URL)

    assert response.headers["access-control-allow-origin"] == CERTFORGE_WEB_URL
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_preflight_does_not_answer_with_a_wildcard_origin(client):
    """`allow_origins=["*"]` echoed `*` back to anyone who asked."""
    response = _preflight(client, "https://evil.example.com")

    assert response.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-origin" not in response.headers


def test_legacy_spa_origin_is_still_allowed(client):
    """SITE_URL serves the live SPA — tightening CORS must not lock it out."""
    from api.core.config import SITE_URL

    origin = SITE_URL or "http://localhost:5173"
    response = _preflight(client, origin)

    assert response.headers["access-control-allow-origin"] == origin


# ── Hardcoded hosts ───────────────────────────────────────────────────────


def test_worker_verify_url_does_not_hardcode_the_legacy_host():
    """The QR code baked into every new credential PDF pointed at the legacy product."""
    import inspect

    from api.core import worker

    source = inspect.getsource(worker)
    assert "certs.intelliforge.tech/verify" not in source


def test_rate_limit_constants_come_from_config():
    """index.py hardcoded its own copies, so the env vars config parsed were dead."""
    from api import index
    from api.core import config

    assert index.RATE_LIMIT == config.RATE_LIMIT
    assert index.RATE_WINDOW == config.RATE_WINDOW
    assert (index.RATE_LIMIT, index.RATE_WINDOW) == (10, 60)
