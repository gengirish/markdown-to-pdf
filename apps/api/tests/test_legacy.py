import pytest
from api.core.legacy_tokens import encode_legacy_token, decode_legacy_token, legacy_cert_id, is_internship_payload

def test_legacy_token_roundtrip():
    payload = {"n": "Alice", "c": "Python 101", "d": "2023-10-01"}
    token = encode_legacy_token(payload)
    
    decoded = decode_legacy_token(token)
    assert decoded == payload

def test_legacy_token_tampering():
    payload = {"n": "Alice"}
    token = encode_legacy_token(payload)
    
    # Tamper with the token
    tampered = "eyJ0ZXN0IjoiYmFkIn0." + token.split(".")[1]
    decoded = decode_legacy_token(tampered)
    assert decoded is None

def test_legacy_cert_id():
    payload = {"n": "Alice", "c": "Python 101", "d": "2023-10-01"}
    cid = legacy_cert_id(payload)
    assert cid.startswith("CERT-")
    assert len(cid) == 17

def test_is_internship_payload():
    assert is_internship_payload({"k": "i"})
    assert not is_internship_payload({"k": "p"})
    assert not is_internship_payload({})
