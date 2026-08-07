import pytest
from pydantic import BaseModel
from api.core.envelope import ApiResponse

class DummyData(BaseModel):
    name: str
    value: int

def test_api_response_ok_dict():
    resp = ApiResponse.ok({"status": "healthy"})
    assert resp.success is True
    assert resp.data == {"status": "healthy"}
    assert resp.error is None

def test_api_response_ok_pydantic():
    data = DummyData(name="test", value=42)
    resp = ApiResponse.ok(data)
    assert resp.success is True
    assert resp.data.name == "test"
    assert resp.data.value == 42

def test_api_response_error():
    resp = ApiResponse.fail("Something went wrong", code=500, error_type="INTERNAL_ERROR")
    assert resp.success is False
    assert resp.data is None
    assert resp.error is not None
    assert resp.error.message == "Something went wrong"
    assert resp.error.type == "INTERNAL_ERROR"
    assert resp.error.code == 500
