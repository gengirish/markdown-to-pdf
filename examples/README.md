# PDF Cert Generator — automation examples

Runnable scripts for certificate issuance, webhooks, admin bulk, and batch verification.

| Variable | Used by | Description |
|----------|---------|-------------|
| `PDFCERT_URL` | All HTTP examples | API base URL (default `http://localhost:8000`) |
| `PDFCERT_API_KEY` | `quickstart.py`, `zapier_integration.py` | `X-API-Key` when server enforces `CERT_API_KEYS` |
| `PDFCERT_ADMIN_KEY` | `bulk_onboarding.py` | `X-Admin-Key` (must match server `ADMIN_KEY`) |

```bash
pip install httpx
```

## Scripts

- **`quickstart.py`** — List courses, create certificate, verify, download PDF
- **`webhook_receiver.py`** — Sample `callback_url` receiver for `certificate.created`
- **`bulk_onboarding.py`** — CSV → admin bulk generate
- **`zapier_integration.py`** — Zapier webhook bridge
- **`batch_verify.py`** — Batch verify tokens from a file

See root `README.md` for full API documentation.
