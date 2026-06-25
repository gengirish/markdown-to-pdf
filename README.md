# PDF Cert Generator

**API-first PDF certificate generation with tamper-proof signed URLs.**

Generate tamper-proof participation and **VTU-style internship completion** certificates as downloadable PDFs with shareable verification links. Certificate data is encoded in the URL itself — signed with HMAC-SHA256, cryptographically verifiable without a database. See [docs/certificate-internship-vtu.md](docs/certificate-internship-vtu.md) for internship fields and college workflow notes. **Offer letter (Word):** [docs/samples/IntelliForge_Internship_Offer_Letter.docx](docs/samples/IntelliForge_Internship_Offer_Letter.docx).

**API docs:** `/docs` · **OpenAPI:** `/openapi.json` · **Agent discovery:** `/llms.txt`

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

- **Stateless** — Certificates live in the URL. No database needed for verification.
- **Tamper-proof** — HMAC-SHA256 signature; any modification is detected.
- **API-first** — OpenAPI docs, `llms.txt`, webhook callbacks, idempotency keys.
- **PDF output** — Download polished certificate PDFs with QR verification codes.
- **Serverless-native** — Runs on Vercel Functions.

---

## Quick Start

```bash
npm install && pip install -r requirements.txt

# Terminal 1 — Backend
python -m uvicorn api.index:app --reload --port 8000

# Terminal 2 — Frontend
npm run dev
```

Open **http://localhost:5173** · API docs at **http://localhost:8000/docs**

---

## API Reference

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/courses` | List available courses |
| `POST` | `/api/certificate` | Create a signed certificate |
| `GET` | `/certificate/{token}` | Public certificate viewer (HTML) |
| `GET` | `/certificate/{token}/download` | Download certificate as PDF |
| `GET` | `/certificate/{token}/verify` | Verify single certificate |
| `POST` | `/api/certificates/verify` | Batch verify certificates |

### Admin Endpoints (requires `X-Admin-Key`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/admin/stats` | Certificate analytics |
| `GET` | `/api/admin/certificates` | List issued certificates |
| `POST` | `/api/admin/certificates/bulk` | Bulk generate (up to 500) |
| `POST` | `/api/admin/certificates/{id}/revoke` | Revoke a certificate |
| `GET` | `/api/admin/courses` | List all courses |
| `POST` | `/api/admin/courses` | Add a course |
| `PATCH` | `/api/admin/courses/{id}` | Toggle course active/inactive |

### Agent Discovery

| Endpoint | Description |
|----------|-------------|
| `GET /openapi.json` | OpenAPI 3.1 specification |
| `GET /llms.txt` | LLM/agent-friendly API description |
| `GET /.well-known/ai-plugin.json` | OpenAI plugin manifest |
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
  "email_sent": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Python SDK

```bash
cd sdk && pip install -e .
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

| Variable | Required | Description |
|----------|----------|-------------|
| `CERT_SECRET_KEY` | **Yes** (prod) | HMAC-SHA256 signing secret |
| `CERT_API_KEYS` | No | Comma-separated API keys for certificate creation |
| `ADMIN_KEY` | No | Admin API authentication key |
| `DATABASE_URL` | No | PostgreSQL for analytics & admin |
| `AGENTMAIL_API_KEY` | No | AgentMail API key for email delivery |
| `AGENTMAIL_INBOX_ID` | No | AgentMail inbox address |
| `FOUNDER_NAME` | No | Signature name on certificates |
| `FOUNDER_TITLE` | No | Signature title under the founder signature |
| `CERT_ORG_TAGLINE` | No | Small org line on certificate header (default: `AN INTELLIFORGE AI INITIATIVE`) |
| `CERT_BRAND_NAME` | No | Main brand on certificates and UI (default: `IntelliForge Learning`) |
| `CERT_PARTICIPATION_TITLE` | No | Certificate type badge (default: `Certificate of Participation`) |
| `CERT_ISSUED_BY` | No | Footer issuer name (defaults to `CERT_BRAND_NAME`) |
| `CERT_WEBSITE` | No | Footer website (default: `learning.intelliforge.tech`) |
| `CERT_INTERNSHIP_ORG` | No | Internship letterhead org (default: `Intelliforge Digital Services`) |
| `CERT_INTERNSHIP_BRAND_PREFIX` | No | Internship brand prefix (default: `IntelliForge`) |
| `CERT_INTERNSHIP_BRAND_ACCENT` | No | Internship brand accent word (default: `Forge`) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7 |
| Backend | FastAPI, Python 3.9+ |
| Database | PostgreSQL — optional |
| PDF | xhtml2pdf |
| QR Codes | python-qrcode, Pillow |
| Email | AgentMail (optional) |
| Crypto | HMAC-SHA256 |
| Hosting | Vercel (serverless) |

---

## License

MIT
