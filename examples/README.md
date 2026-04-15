# IntelliForge Certificates — automation examples

Small, runnable scripts that show **API-first** flows: idempotent issuance, webhooks, admin bulk, no-code bridges, and batch verification. Each script is standalone (no SDK).

Shared environment variables:

| Variable | Used by | Description |
|----------|---------|-------------|
| `INTELLIFORGE_URL` | All HTTP examples | API base URL for your IntelliForge Certificate deployment |
| `INTELLIFORGE_API_KEY` | `quickstart.py`, `zapier_integration.py` | `X-API-Key` when your deployment enforces `CERT_API_KEYS` |
| `INTELLIFORGE_ADMIN_KEY` | `bulk_onboarding.py` | `X-Admin-Key` (must match server `ADMIN_KEY`) |

Install dependencies as needed:

```bash
pip install httpx
pip install fastapi uvicorn   # webhook_receiver only
pip install flask httpx       # zapier_integration only
```

---

## `quickstart.py`

Lists courses, creates one certificate with an `idempotency_key`, verifies it, downloads the PDF, prints URLs.

```bash
set INTELLIFORGE_API_KEY=your-key
python quickstart.py
```

Requires only `httpx`. Writes `quickstart_certificate.pdf` in the current directory.

---

## `webhook_receiver.py`

FastAPI app on **port 9000** with `POST /webhook` for `callback_url` automation. Logs `certificate.created` payloads; extend `handle_certificate_created()` for Slack, CRM, or email.

```bash
pip install fastapi uvicorn
python webhook_receiver.py
```

Expose with ngrok (or similar) and pass `callback_url` when calling `POST /api/certificate`.

---

## `bulk_onboarding.py`

Reads a CSV of participants and calls `POST /api/admin/certificates/bulk`. Writes a results CSV with `url` / `download_url` for each row.

**CSV format** (header required):

```text
name,email,course,completion_date
Jane Doe,jane@example.com,AI Product Development Fundamentals,2026-04-15
```

`completion_date` is optional (defaults to today). Course names must match active courses from `GET /api/courses`.

**Server requirement:** bulk admin needs **`DATABASE_URL`** on the API host; otherwise the endpoint returns 503.

```bash
set INTELLIFORGE_ADMIN_KEY=your-admin-key
python bulk_onboarding.py participants.csv -o out.csv
```

---

## `zapier_integration.py`

Flask handler for Zapier “Webhooks by Zapier” (form POST). Creates a certificate and returns JSON fields Zapier can use in the next step (`certificate_url`, `download_url`, etc.).

Form fields: `participant_name`, `course_name`, `completion_date`; optional `instructor_name`, `participant_email`.

```bash
set INTELLIFORGE_API_KEY=your-key
python zapier_integration.py
```

Default listen: `http://0.0.0.0:8080/zapier/certificate`. Point Zapier’s POST action at that URL.

---

## `batch_verify.py`

Reads certificate tokens (one per line) from a file or **stdin**, calls `POST /api/certificates/verify` in chunks of 100, prints a **compliance-style** summary (valid / invalid / revoked).

```bash
python batch_verify.py tokens.txt
type tokens.txt | python batch_verify.py
```

No API key required for verification on the public API.

---

## Why this is “automation-ready”

- **Idempotency** — safe retries for agents and cron jobs.  
- **Webhooks** — push `certificate.created` into any stack without polling.  
- **Batch verify** — audit thousands of credentials without N round-trips to “single verify”.  
- **Admin bulk** — one HTTP call for up to 500 rows (enterprise onboarding).  
- **Open discovery** — `GET /openapi.json`, `GET /llms.txt` for tools and LLMs.

For full API detail, see the project root `README.md` or your deployment’s OpenAPI/Swagger docs at `/docs`.
