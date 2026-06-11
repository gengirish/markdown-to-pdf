# pdfcert (Python SDK)

Python client for the **PDF Cert Generator API**. Version **2.0.0** tracks API **v2.0.0**.

## Install

From the `sdk` directory:

```bash
pip install .
```

Or in editable mode:

```bash
pip install -e .
```

Requires **Python 3.9+** and **httpx**.

## Quick start

```python
from pdfcert import PdfCert, ValidationError

client = PdfCert(base_url="http://localhost:8000")
print(client.health())
print(client.list_courses())

cert = client.create_certificate(
    participant_name="Ada Lovelace",
    course_name="API Design Workshop",
    completion_date="2026-04-15",
)
print(cert["download_url"])

pdf_bytes = client.download_pdf(cert["token"])
client.download_pdf(cert["token"], path="certificate.pdf")

admin_client = PdfCert(admin_key="your-admin-key", base_url="http://localhost:8000")
stats = admin_client.admin.stats()
```

### Context manager

```python
with PdfCert(base_url="http://localhost:8000") as client:
    client.create_certificate(...)
```

## Authentication

| Header        | When                         |
|---------------|------------------------------|
| `X-API-Key`   | `create_certificate` (if server enforces keys) |
| `X-Admin-Key` | All `client.admin.*` methods |

## Errors

| Exception              | Typical cause                          |
|------------------------|----------------------------------------|
| `PdfCertError`         | Base class; transport/other API errors |
| `AuthenticationError`  | HTTP 401 / 403                         |
| `RateLimitError`       | HTTP 429                               |
| `ValidationError`      | HTTP 400 / 422                         |

## API reference (SDK)

- `PdfCert(api_key=None, admin_key=None, base_url="http://localhost:8000")`
- `health()` → `dict`
- `list_courses()` → `list[str]`
- `create_certificate(...)` → `dict`
- `verify(token)` → `dict`
- `batch_verify(tokens)` → `dict`
- `download_pdf(token, path=None)` → `bytes` if `path` is omitted
- `admin.stats()`, `admin.list_certificates(...)`, `admin.bulk_generate(entries)`, `admin.revoke(id)`, `admin.list_courses()`, `admin.add_course(name)`, `admin.toggle_course(course_id, active)` → `dict`
