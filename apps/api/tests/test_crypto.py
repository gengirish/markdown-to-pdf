import pytest
from api.core.crypto import generate_credential_id, is_certforge_id, hmac_sign, hmac_verify, hash_api_key

def test_generate_credential_id():
    cid = generate_credential_id()
    assert cid.startswith("CF-")
    assert len(cid) == 16
    assert is_certforge_id(cid)

def test_is_certforge_id():
    assert is_certforge_id("CF-2026-ABCDEF12")
    assert not is_certforge_id("CERT-ABCDEF123456")
    assert not is_certforge_id("some-random-string")

def test_hmac_sign_and_verify():
    payload = "test-payload"
    signature = hmac_sign(payload)
    assert signature is not None
    assert hmac_verify(payload, signature)
    assert not hmac_verify("wrong-payload", signature)
    assert not hmac_verify(payload, "wrong-signature")

def test_hash_api_key():
    key = "pk_test_123"
    hashed = hash_api_key(key)
    assert hashed != key
    assert len(hashed) == 64 # SHA-256 hex length
