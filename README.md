# CertForge

**Verifiable credentials, API-first.**

CertForge issues tamper-proof certificates as PDFs with shareable verification links.
Certificate data is signed with HMAC-SHA256 and encoded in the URL itself, so a
document can be verified cryptographically without a database lookup.

Three certificate kinds are supported — **participation**, **VTU-style internship
completion**, and **event appreciation** — plus GST tax invoices. See
[docs/certificate-internship-vtu.md](docs/certificate-internship-vtu.md) for the
internship fields and college workflow notes. **Offer letter (Word):**
[docs/samples/IntelliForge_Internship_Offer_Letter.docx](docs/samples/IntelliForge_Internship_Offer_Letter.docx).

**API docs:** `/docs` · **OpenAPI:** `/openapi.json` · **Agent discovery:** `/llms.txt` · **Sitemap:** `/sitemap.xml`

---

## How It Works

```
1. POST /api/certificate              → Signed token + shareable URL
2. GET  /certificate/{token}          → Public viewer page (HTML)
3. GET  /certificate/{token}/download → PDF with embedded QR code
4. GET  /certificate/{token}/verify   → JSON verification
5. POST /api/certificates/verify      → Batch verification
```

### Features

- **Stateless** — certificates live in the URL. No database needed for verification.
- **Tamper-proof** — HMAC-SHA256 signature; any modification is detected.
- **API-first** — OpenAPI docs, `llms.txt`, webhook callbacks, idempotency keys.
- **PDF output** — polished certificate PDFs with QR verification codes.
- **Multi-tenant** — an organization/template/credential API under `/api/v1`, with
  public passports, Open Badges 3.0 badge JSON, scoped API keys and webhooks.

---

## Repository

```
apps/api/          FastAPI backend. Docker image deployed to Fly.io.
apps/legacy-web/   Vite + React 19 SPA — the live certificate generator UI.
apps/web/          Next.js 16 + Clerk — the CertForge dashboard (in development).
sdk/               Installable Python client (`pdfcert`).
examples/          Bulk onboarding, batch verify, webhook receiver, Zapier.
e2e/               Playwright specs.
```

## Quick Start

```bash
npm install
pip install -r apps/api/requirements.txt

# Terminal 1 — backend
cd apps/api && python -m uvicorn api.index:app --reload --port 8000

# Terminal 2 — frontend (its dev proxy forwards /api, /certificate, /invoice to :8000)
cd apps/legacy-web && npm run dev
```

Open **http://localhost:5173** · API docs at **http://localhost:8000/docs**

Build the frontend with `npm run build:web` from the repo root; the output lands in
`apps/legacy-web/dist`.

### Tests

```bash
cd apps/api && python -m pytest      # unit suite, no live server required
cd apps/api && python test_api.py    # integration script; needs the API on :8000
python sdk/test_sdk.py               # SDK suite, after `pip install -e ./sdk`
npm run test:e2e                     # Playwright; starts the API and SPA itself
ruff check apps/api/api/ sdk/pdfcert/
```

---

## API Reference

### Certificates and invoices

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/info` | Branding and capability info |
| `GET` | `/api/courses` | List available courses |
| `POST` | `/api/certificate` | Create a signed certificate |
| `GET` | `/certificate/{token}` | Public certificate viewer (HTML) |
| `GET` | `/certificate/{token}/download` | Download certificate as PDF |
| `GET` | `/certificate/{token}/verify` | Verify a single certificate |
| `POST` | `/api/certificates/verify` | Batch verify certificates |
| `POST` | `/api/invoice` | Create a signed invoice |
| `GET` | `/invoice/{token}/download` | Download invoice as PDF |

### CertForge `/api/v1` (Clerk session auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/orgs` | Create an organization |
| `GET` `PATCH` | `/api/v1/orgs/{slug}` | Read / update an organization |
| `GET` | `/api/v1/orgs/{slug}/members` | List members |
| `GET` | `/api/v1/templates` | List built-in templates |
| `GET` `POST` | `/api/v1/orgs/{slug}/templates` | List / create org templates |
| `GET` `PATCH` `DELETE` | `/api/v1/orgs/{slug}/templates/{template_id}` | Read / update / delete a template |
| `POST` | `/api/v1/orgs/{slug}/templates/{template_id}/default` | Make a template the org default |
| `POST` | `/api/v1/orgs/{slug}/templates/import/{global_id}` | Copy a built-in template into the org |
| `POST` | `/api/v1/orgs/{slug}/templates/preview` | Render a sample PDF of a template |
| `POST` | `/api/v1/orgs/{slug}/templates/from-image` | Read an uploaded design with a model and propose a layout |
| `POST` `DELETE` | `/api/v1/orgs/{slug}/logo` | Upload / remove the logo printed on this org's certificates |
| `GET` `POST` | `/api/v1/orgs/{slug}/template-assets` | List / upload certificate artwork |
| `GET` | `/api/v1/orgs/{slug}/template-assets/{asset_id}/image` | Fetch stored artwork |
| `DELETE` | `/api/v1/orgs/{slug}/template-assets/{asset_id}` | Delete artwork (refused while a template uses it) |
| `GET` `POST` | `/api/v1/orgs/{slug}/credentials` | List issued credentials / issue one |
| `GET` | `/api/v1/orgs/{slug}/credentials/{public_id}` | Read a single credential |
| `POST` | `/api/v1/orgs/{slug}/credentials/{public_id}/revoke` | Revoke a credential |
| `POST` | `/api/v1/orgs/{slug}/credentials/bulk` | Queue a bulk issuance batch |
| `GET` | `/api/v1/orgs/{slug}/batches/{batch_id}` | Batch progress |
| `POST` `GET` `DELETE` | `/api/v1/orgs/{slug}/api-keys` | Manage API keys |
| `POST` `GET` `DELETE` | `/api/v1/orgs/{slug}/webhooks` | Manage webhook endpoints |
| `GET` | `/api/v1/passports/{username}` | Public credential passport |
| `POST` | `/api/v1/claims/{credential_id}` | Claim a credential into a passport |
| `POST` | `/api/v1/orgs/{slug}/checkout` | Start a billing checkout |
| `GET` | `/api/v1/verify/{credential_id}` | Verify a credential (JSON) |

Every `/api/v1` response uses one envelope:

```json
{ "success": true, "data": {}, "error": null, "meta": null }
```

### Public credential URLs

Served at the site root, with no auth — the ID is the capability, the same posture
as the legacy download route. These are the URLs that go inside a printed QR code,
so they are also the ones `vercel.json` must rewrite through to the API.

| Endpoint | Description |
|----------|-------------|
| `GET /verify/{credential_id}` | Human-readable verification page |
| `GET /credentials/{public_id}/badge.json` | Open Badges 3.0 badge |
| `GET /credentials/{public_id}/pdf` | The certificate, rendered on demand — nothing is stored |
| `GET /credentials/{public_id}/qr.png` | QR code pointing at the verification page |
| `GET /orgs/{slug}` | Public issuer profile (an Open Badges `issuer.id` dereferences here) |
| `GET /orgs/{slug}/logo` | The organization's uploaded logo — the same image its certificates print |

Every route that renders a credential's *contents* — the verification page,
`badge.json` and the PDF — verifies its HMAC signature first and answers **409**
with `error.type = "signature_mismatch"` if it does not match. `qr.png` encodes only
the verification URL, so it checks status alone; `/orgs/{slug}` is not
credential-scoped and content-negotiates between an Open Badges Profile
(`Accept: application/json`) and an HTML page.

### Legacy admin endpoints (requires `X-Admin-Key` and a database)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/admin/stats` | Certificate analytics |
| `GET` | `/api/admin/certificates` | List issued certificates |
| `POST` | `/api/admin/certificates/bulk` | Bulk generate (up to 500) |
| `POST` | `/api/admin/certificates/{id}/revoke` | Revoke a certificate |
| `GET` `POST` | `/api/admin/courses` | List / add courses |
| `PATCH` | `/api/admin/courses/{id}` | Toggle a course active/inactive |

### Agent Discovery

| Endpoint | Description |
|----------|-------------|
| `GET /openapi.json` | OpenAPI 3.1 specification |
| `GET /llms.txt` | LLM/agent-friendly API description |
| `GET /.well-known/ai-plugin.json` | AI plugin manifest |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

---

## Create a Certificate

```bash
curl -X POST http://localhost:8000/api/certificate \
  -H "Content-Type: application/json" \
  -d '{
    "participant_name": "Jane Doe",
    "course_name": "AI Product Development Fundamentals",
    "completion_date": "2026-04-15",
    "instructor_name": "Certificate Team",
    "participant_email": "jane@example.com",
    "callback_url": "https://your-server.com/webhook",
    "idempotency_key": "unique-request-id"
  }'
```

Response:

```json
{
  "certificate_id": "CERT-A1B2C3D4E5F6",
  "token": "eyJjIjoi...",
  "url": "http://localhost:8000/certificate/eyJjIjoi...",
  "download_url": "http://localhost:8000/certificate/eyJjIjoi.../download",
  "participant_name": "Jane Doe",
  "course_name": "AI Product Development Fundamentals",
  "certificate_kind": "participation",
  "email_sent": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

`course_name` must be one of the values returned by `/api/courses`. Errors on these
endpoints come back as `{"error": {"code": 400, "message": "…", "type": "…"}}`.

When `CERT_API_KEYS` is set, requests need a matching `X-API-Key` header unless they
originate from the deployment's own web UI. Rate limiting is 10 requests per 60
seconds per client IP by default.

---

## Python SDK

```bash
pip install -e ./sdk
```

```python
from pdfcert import PdfCert

client = PdfCert(base_url="http://localhost:8000")
cert = client.create_certificate(
    participant_name="Ada Lovelace",
    course_name="API Design Workshop",
    completion_date="2026-04-15",
)
client.download_pdf(cert["token"], path="certificate.pdf")
```

See [`sdk/README.md`](sdk/README.md) for full SDK documentation.

---

## Environment Variables

Copy [`.env.example`](.env.example) as a starting point.

| Variable | Required | Description |
|----------|----------|-------------|
| `CERT_SECRET_KEY` | **Yes** (prod) | HMAC-SHA256 signing secret. Changing it invalidates every certificate already issued |
| `ENV` | For prod | Set to `production`. Without it the API treats itself as dev and falls back to insecure defaults |
| `CERT_API_KEYS` | No | Comma-separated API keys for certificate creation |
| `ADMIN_KEY` | No | Admin API authentication key |
| `DATABASE_URL` | No | PostgreSQL. Required for `/api/v1`, analytics, admin, and background issuance; the certificate and invoice endpoints work without it |
| `CLERK_SECRET_KEY` | No | Clerk backend API key |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | For dashboard auth | Clerk publishable key; the JWKS URL used to verify session tokens is derived from it |
| `CLERK_JWKS_URL` | No | Explicit JWKS override. Without this (or the publishable key) authenticated endpoints answer 503 — they never fall back to unverified tokens |
| `CLERK_WEBHOOK_SECRET` | No | Clerk webhook signing secret for org sync |
| `RAZORPAY_WEBHOOK_SECRET` | For billing | Razorpay webhook signing secret. **No default**: unset means `/api/v1/webhooks/razorpay` rejects every request, because a valid signature upgrades an org's tier |
| `RATE_LIMIT_MAX_REQUESTS` | No | Requests per window per client IP (default: `10`) |
| `RATE_LIMIT_WINDOW_SECONDS` | No | Rate-limit window in seconds (default: `60`) |
| `TRUSTED_PROXY_HOPS` | No | Reverse proxies in front of the app, used to pick the caller out of `X-Forwarded-For` (default: `2`, for browser → Vercel → Fly). Set to `0` to ignore forwarding headers |
| `AGENTMAIL_API_KEY` | No | AgentMail API key for email delivery |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | For template artwork | Cloudflare R2, where an uploaded certificate design is stored. All four (or `R2_ENDPOINT` in place of the account id) or none: unset means the upload endpoint answers 503. There is **no local-filesystem fallback** — a storage backend that differs between dev and production works everywhere it is tested and loses every image on a Fly machine that scales to zero. `GET /api/health?deep=storage` asks whether the bucket actually answers, which is a different claim from the variables being set |
| `R2_ENDPOINT` | No | S3-compatible endpoint override, for a local MinIO. Otherwise derived from `R2_ACCOUNT_ID` |
| `ANTHROPIC_API_KEY` | For design reading | Powers `POST /orgs/{slug}/templates/from-image`, which reads an uploaded certificate design and proposes where each field goes. Unset means that one endpoint answers 503; every other way of building a template still works |
| `VISION_IMPORTS_PER_MONTH` | No | Design readings per org per calendar month (default: `10`). Each one is a paid model call at roughly $0.05–0.20, and billing is still mocked, so this is what bounds the spend |
| `AGENTMAIL_INBOX_ID` | No | AgentMail inbox address |
| `PROCRASTINATE_APPLY_SCHEMA` | No | `1` applies the job-queue schema on boot. Deployments leave it `0` and apply it in the release step |
| `SITE_URL` | No | Canonical public URL of the certificate product (e.g. `https://certs.intelliforge.tech`). Printed QR codes resolve through it, so it must never be repointed once certificates are in the wild |
| `CERTFORGE_WEB_URL` | No | CertForge dashboard and public credential pages (default: `https://certforge.intelliforge.tech`) |
| `CERTFORGE_API_URL` | No | Machine-facing API host (default: `https://api.certforge.intelliforge.tech`) |
| `CONTACT_EMAIL` | No | Contact email in the AI plugin manifest (default: `support@intelliforge.tech`) |
| `FOUNDER_NAME` | No | Signature name on certificates |
| `FOUNDER_TITLE` | No | Signature title under the founder signature (default: `Founder, Intelliforge AI`) |
| `CERT_ORG_TAGLINE` | No | Small org line on the certificate header (default: `AN INTELLIFORGE AI INITIATIVE`) |
| `CERT_BRAND_NAME` | No | Main brand on certificates and UI (default: `IntelliForge Learning`) |
| `CERT_PARTICIPATION_TITLE` | No | Certificate type badge (default: `Certificate of Participation`) |
| `CERT_ISSUED_BY` | No | Footer issuer name (defaults to `CERT_BRAND_NAME`) |
| `CERT_WEBSITE` | No | Footer website (default: `learning.intelliforge.tech`) |
| `CERT_INTERNSHIP_ORG` | No | Internship letterhead org (default: `Intelliforge Digital Services`) |
| `CERT_INTERNSHIP_BRAND_PREFIX` | No | Internship brand prefix (default: `IntelliForge`) |
| `CERT_INTERNSHIP_BRAND_ACCENT` | No | Internship brand accent word (default: `Forge`) |
| `CERT_APPRECIATION_*` | No | Appreciation certificate org, titles and colors — see `apps/api/api/core/config.py` |

Branding is entirely env-driven. Nothing brand-specific is hardcoded in the templates.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.13 (Docker image), deployed on Fly.io |
| Certificate UI | React 19, Vite 7 — served by Vercel, which rewrites API paths to Fly |
| Dashboard | Next.js 16, Clerk, Tailwind CSS 4 |
| Database | PostgreSQL (Neon) — psycopg2 for the legacy tables, SQLAlchemy 2.0 + Alembic for CertForge |
| Background jobs | Procrastinate, embedded in the API lifespan |
| PDF | xhtml2pdf, ReportLab |
| QR Codes | python-qrcode, Pillow |
| Email | AgentMail (optional) |
| Crypto | HMAC-SHA256; Clerk RS256 session tokens |
| Monorepo | npm workspaces + turbo |

---

## License

MIT
