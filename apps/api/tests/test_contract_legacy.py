"""The freeze contract, expressed as tests.

certs.intelliforge.tech is a live product. Certificates have been issued, and
their QR codes are printed on paper — nobody can reissue those. So the legacy
surface is frozen: `sdk/pdfcert` parses its response shapes verbatim, and the
tokens themselves must keep decoding forever.

This is the file that makes index.py safe to touch. Phase 0 called for it and it
was never written, which is why the plan's Phase 6 consolidation and the CDN
caching work have both been sitting behind "we can't verify we didn't break
anything".

Two kinds of assertion here, and the distinction matters:

  SHAPE   the keys a response must carry. Values are not pinned, because
          branding is environment-driven and a deployment may legitimately
          differ. Extra keys are allowed — adding a field is backwards
          compatible; removing or renaming one is not.

  EXACT   the error envelope and the token encoding. These are pinned to the
          byte, because a client parses them positionally.
"""

import base64
import hashlib
import hmac
import json

import pytest

# The secret these fixtures were generated against. It is NOT a production
# value and must never change: the pinned tokens below were produced with it,
# and regenerating them would defeat the entire point of the file.
FROZEN_SECRET = "contract-test-frozen-secret-do-not-change"


# Tokens produced by the real encoder, committed as literals. If someone
# renames a payload key, reorders the JSON, changes the separators, or alters
# the signing input, these stop decoding — which is exactly what nothing else
# in the suite would notice.
FROZEN_TOKENS = {
    "participation": {
        "payload": {
            "n": "Ada Lovelace",
            "c": "AI Product Development Fundamentals",
            "d": "2026-03-14",
            "i": "IntelliForge AI Team",
        },
        "token": "eyJjIjoiQUkgUHJvZHVjdCBEZXZlbG9wbWVudCBGdW5kYW1lbnRhbHMiLCJkIjoiMjAyNi0wMy0xNCIsImkiOiJJbnRlbGxpRm9yZ2UgQUkgVGVhbSIsIm4iOiJBZGEgTG92ZWxhY2UifQ.9497a6a9e1f23addb68749de02e3c99604ac5174521762fe9309a1e10a997b67",
        "cert_id": "CERT-6F67A05BEF04",
    },
    "internship": {
        "payload": {
            "k": "i",
            "n": "Bhavya Rao",
            "c": "VTU Industry Internship",
            "d": "2026-05-02",
            "i": "IntelliForge AI Team",
            "u": "1AB21CS001",
            "w": "4 weeks",
            "h": "160",
            "m": "Girish Hiremath",
            "s": "BMS College of Engineering",
        },
        "token": "eyJjIjoiVlRVIEluZHVzdHJ5IEludGVybnNoaXAiLCJkIjoiMjAyNi0wNS0wMiIsImgiOiIxNjAiLCJpIjoiSW50ZWxsaUZvcmdlIEFJIFRlYW0iLCJrIjoiaSIsIm0iOiJHaXJpc2ggSGlyZW1hdGgiLCJuIjoiQmhhdnlhIFJhbyIsInMiOiJCTVMgQ29sbGVnZSBvZiBFbmdpbmVlcmluZyIsInUiOiIxQUIyMUNTMDAxIiwidyI6IjQgd2Vla3MifQ.888484f2e56a9f25038af6126d12ddc997c3eb53be7f1933f5bbe70cd68e3dbb",
        "cert_id": "CERT-1AFCD4AC5FCA",
    },
    "appreciation": {
        "payload": {
            "k": "a",
            "n": "Chetan Kumar",
            "c": "Sports Day 2026",
            "d": "2026-08-15",
            "i": "IntelliForge AI Team",
            "r": "outstanding sportsmanship",
            "e": "Annual Sports Meet",
            "v": "Sobha Dream Gardens",
            "p": "maidaan.academy",
        },
        "token": "eyJjIjoiU3BvcnRzIERheSAyMDI2IiwiZCI6IjIwMjYtMDgtMTUiLCJlIjoiQW5udWFsIFNwb3J0cyBNZWV0IiwiaSI6IkludGVsbGlGb3JnZSBBSSBUZWFtIiwiayI6ImEiLCJuIjoiQ2hldGFuIEt1bWFyIiwicCI6Im1haWRhYW4uYWNhZGVteSIsInIiOiJvdXRzdGFuZGluZyBzcG9ydHNtYW5zaGlwIiwidiI6IlNvYmhhIERyZWFtIEdhcmRlbnMifQ.2746f21cf56b206e591b2d347fc7658552e3ffad67f26e16ee535bfcbe92fb98",
        "cert_id": "CERT-86EB86549D5D",
    },
}

#: Every single-letter key the format has ever assigned. Renaming, reordering or
#: repurposing one invalidates certificates already in circulation.
FROZEN_KEYS = set("ncdikuwhmsrevp")


@pytest.fixture
def frozen_secret(monkeypatch):
    """Point the app at the secret the fixtures were signed with."""
    import api.core.config as config
    import api.core.crypto as crypto
    import api.core.legacy_tokens as legacy
    import api.index as index

    for module in (config, crypto, legacy, index):
        if hasattr(module, "CERT_SECRET"):
            monkeypatch.setattr(module, "CERT_SECRET", FROZEN_SECRET)
    monkeypatch.setenv("CERT_SECRET_KEY", FROZEN_SECRET)


# -- the token format --------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(FROZEN_TOKENS))
def test_a_token_issued_earlier_still_decodes(kind, frozen_secret):
    """The single most important assertion in the repository.

    These tokens stand in for every certificate already printed. If this fails,
    certificates in the world have stopped verifying.
    """
    from api.index import _decode_cert

    case = FROZEN_TOKENS[kind]
    assert _decode_cert(case["token"]) == case["payload"]


@pytest.mark.parametrize("kind", sorted(FROZEN_TOKENS))
def test_the_printed_certificate_id_is_unchanged(kind, frozen_secret):
    """_cert_id is what appears on the PDF; it must be reproducible forever."""
    from api.index import _cert_id

    case = FROZEN_TOKENS[kind]
    assert _cert_id(case["payload"]) == case["cert_id"]


@pytest.mark.parametrize("kind", sorted(FROZEN_TOKENS))
def test_re_encoding_reproduces_the_same_token(kind, frozen_secret):
    """Encoding is deterministic: same payload, same secret, same bytes."""
    from api.index import _encode_cert

    case = FROZEN_TOKENS[kind]
    assert _encode_cert(case["payload"]) == case["token"]


def test_a_tampered_payload_is_rejected(frozen_secret):
    from api.index import _decode_cert

    token = FROZEN_TOKENS["participation"]["token"]
    payload, sig = token.rsplit(".", 1)
    raw = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    raw["n"] = "Somebody Else"
    forged = (
        base64.urlsafe_b64encode(
            json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    assert _decode_cert(f"{forged}.{sig}") is None


def test_the_signature_is_hmac_sha256_over_the_payload(frozen_secret):
    """Pin the algorithm, not just the outcome."""
    case = FROZEN_TOKENS["participation"]
    payload, sig = case["token"].rsplit(".", 1)
    expected = hmac.new(
        FROZEN_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert sig == expected


def test_no_payload_key_has_been_repurposed(frozen_secret):
    """Every key in the fixtures must be one the format already assigned."""
    for case in FROZEN_TOKENS.values():
        assert set(case["payload"]) <= FROZEN_KEYS


# -- response shapes ---------------------------------------------------------

def must_have(body: dict, keys: set, where: str):
    missing = keys - set(body)
    assert not missing, f"{where} lost frozen key(s): {sorted(missing)}"


def test_health_shape(client):
    body = client.get("/api/health").json()
    must_have(body, {"status", "service", "version", "dependencies"}, "/api/health")
    must_have(body["dependencies"], {"database", "email"}, "/api/health dependencies")


def test_info_shape(client):
    body = client.get("/api/info").json()
    must_have(body, {"name", "version", "description", "branding"}, "/api/info")


def test_courses_shape(client):
    body = client.get("/api/courses").json()
    must_have(body, {"courses"}, "/api/courses")
    assert isinstance(body["courses"], list)


def test_certificate_verify_shape(client, frozen_secret):
    token = FROZEN_TOKENS["participation"]["token"]
    body = client.get(f"/certificate/{token}/verify").json()
    must_have(body, {"valid"}, "/certificate/{token}/verify")
    assert body["valid"] is True


def test_certificate_verify_rejects_a_bad_token(client):
    body = client.get("/certificate/not.a.real.token/verify").json()
    assert body["valid"] is False
    must_have(body, {"valid", "message"}, "/certificate/{token}/verify (invalid)")


def test_batch_verify_shape(client, frozen_secret):
    token = FROZEN_TOKENS["participation"]["token"]
    body = client.post(
        "/api/certificates/verify", json={"tokens": [token, "bogus.token"]}
    ).json()
    must_have(body, {"results"}, "/api/certificates/verify")
    assert len(body["results"]) == 2


# -- the error envelope ------------------------------------------------------

def test_legacy_errors_are_bare_and_exact(client):
    """EXACT, not shape. sdk/pdfcert reads error.code and error.message
    positionally, and a `success` key here would mean the v1 envelope has
    leaked onto the frozen surface."""
    r = client.get("/invoice/not.a.real.token/download")
    body = r.json()

    assert set(body) == {"error"}, f"legacy error grew keys: {sorted(body)}"
    assert set(body["error"]) == {"code", "message", "type"}
    assert body["error"]["code"] == 404
    assert isinstance(body["error"]["message"], str)
    assert "success" not in body


def test_the_v1_envelope_has_not_leaked_onto_any_legacy_path(client):
    for path in (
        "/invoice/not.a.real.token/download",
        "/certificate/nope.nope/download",
    ):
        body = client.get(path).json()
        assert "success" not in body, f"{path} gained a success key"


# -- the frozen route table --------------------------------------------------

def test_every_frozen_route_still_exists():
    """A route disappearing is the failure this catches — a rename in
    index.py, or a router that stopped being registered."""
    from api.index import app

    paths = {r.path for r in app.routes}
    for path in {
        "/api/health",
        "/api/info",
        "/api/courses",
        "/api/certificate",
        "/api/invoice",
        "/api/certificates/verify",
        "/certificate/{token}",
        "/certificate/{token}/download",
        "/certificate/{token}/verify",
        "/invoice/{token}/download",
        "/api/admin/stats",
        "/api/admin/certificates",
        "/api/admin/courses",
    }:
        assert path in paths, f"frozen route disappeared: {path}"
