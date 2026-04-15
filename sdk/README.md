# intelliforge (Python SDK)

Python client for the **IntelliForge Certificate API** (`https://certs.intelliforge.tech`). Version **2.0.0** tracks API **v2.0.0**.

## Install

From the `sdk` directory (this folder):

```bash
pip install .
```

Or in editable mode while developing:

```bash
pip install -e .
```

Requires **Python 3.9+** and **httpx**.

## Quick start

```python
from intelliforge import IntelliForge, ValidationError

# Public calls: no key required
client = IntelliForge()
print(client.health())
print(client.list_courses())

# Certificate creation: set api_key (sent as X-API-Key)
client = IntelliForge(api_key="your-api-key")
cert = client.create_certificate(
    participant_name="Ada Lovelace",
    course_name="API Design Workshop",
    completion_date="2026-04-15",
)
print(cert["download_url"])

# Verify
info = client.verify(cert["token"])

# Download PDF to memory or disk
pdf_bytes = client.download_pdf(cert["token"])
client.download_pdf(cert["token"], path="certificate.pdf")

# Batch verify
print(client.batch_verify(["token-one", "token-two"]))

# Admin (X-Admin-Key)
admin_client = IntelliForge(admin_key="your-admin-key")
stats = admin_client.admin.stats()
certs = admin_client.admin.list_certificates(limit=10, course="API Design Workshop")
```

### Context manager

The underlying HTTP client is closed when you exit the block:

```python
with IntelliForge(api_key="...") as client:
    client.create_certificate(...)
```

## Authentication

| Header        | When                         |
|---------------|------------------------------|
| `X-API-Key`   | `create_certificate`         |
| `X-Admin-Key` | All `client.admin.*` methods |

If a required key is missing, `AuthenticationError` is raised before the HTTP call.

## Errors

| Exception              | Typical cause                          |
|------------------------|----------------------------------------|
| `IntelliForgeError`    | Base class; transport/other API errors |
| `AuthenticationError`  | HTTP 401 / 403                         |
| `RateLimitError`       | HTTP 429                               |
| `ValidationError`      | HTTP 400 / 422                         |

All carry `status_code` and `response_body` when the failure came from an HTTP response.

## API reference (SDK)

- `IntelliForge(api_key=None, admin_key=None, base_url="https://certs.intelliforge.tech")`
- `health()` → `dict`
- `list_courses()` → `list[str]`
- `create_certificate(...)` → `dict`
- `verify(token)` → `dict`
- `batch_verify(tokens)` → `dict`
- `download_pdf(token, path=None)` → `bytes` if `path` is omitted, else writes file and returns `None`
- `admin.stats()`, `admin.list_certificates(...)`, `admin.bulk_generate(entries)`, `admin.revoke(id)`, `admin.list_courses()`, `admin.add_course(name, description="")`, `admin.toggle_course(course_id, active)` → `dict`

See the IntelliForge Certificate API documentation for request/response field details.
