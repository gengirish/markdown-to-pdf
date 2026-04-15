# IntelliForge Certificates

**API-first verifiable credentials with zero vendor lock-in.**

Generate tamper-proof participation certificates with shareable URLs. All certificate data lives inside the URL itself — signed with HMAC-SHA256, cryptographically verifiable without a database.

**Live:** [md2pdf.intelliforge.tech](https://md2pdf.intelliforge.tech) · **Docs:** [/docs](https://md2pdf.intelliforge.tech/docs) · **OpenAPI:** [/openapi.json](https://md2pdf.intelliforge.tech/openapi.json) · **Agent discovery:** [/llms.txt](https://md2pdf.intelliforge.tech/llms.txt)

---

## How It Works

```
1. POST /api/certificate              → Signed token + shareable URL
2. GET  /certificate/{token}          → Public viewer page (HTML)
3. GET  /certificate/{token}/download → PDF with embedded QR code
4. GET  /certificate/{token}/verify   → JSON verification
5. POST /api/certificates/verify      → Batch verification
```

### What makes this different

- **Stateless** — Certificates live in the URL. No database needed for verification.
- **Tamper-proof** — HMAC-SHA256 signature; any modification is detected.
- **API-first** — OpenAPI docs, `llms.txt`, webhook callbacks, idempotency keys.
- **Agent-friendly** — Structured for LLM/agent consumption with discovery endpoints.
- **Privacy-first** — QR codes rendered server-side, no third-party calls.
- **Serverless-native** — Runs on Vercel Functions with zero cold-start state.

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

Interactive docs available at [`/docs`](https://md2pdf.intelliforge.tech/docs) (Swagger UI) and [`/redoc`](https://md2pdf.intelliforge.tech/redoc).

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
| `POST` | `/api/convert` | Markdown → PDF conversion |

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
curl -X POST https://md2pdf.intelliforge.tech/api/certificate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "participant_name": "Jane Doe",
    "course_name": "AI Product Development Fundamentals",
    "completion_date": "2026-04-15",
    "instructor_name": "IntelliForge AI Team",
    "participant_email": "jane@example.com",
    "callback_url": "https://your-server.com/webhook",
    "idempotency_key": "unique-request-id"
  }'
```

Response:

```json
{
  "certificate_id": "IF-A1B2C3D4E5F6",
  "token": "eyJjIjoi...",
  "url": "https://md2pdf.intelliforge.tech/certificate/eyJjIjoi...",
  "download_url": "https://md2pdf.intelliforge.tech/certificate/eyJjIjoi.../download",
  "participant_name": "Jane Doe",
  "course_name": "AI Product Development Fundamentals",
  "email_sent": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Automation Features

**Idempotency** — Pass `idempotency_key` to safely retry requests. Cached for 1 hour.

```bash
# Both requests return the same certificate
curl -X POST .../api/certificate -d '{"idempotency_key": "order-123", ...}'
curl -X POST .../api/certificate -d '{"idempotency_key": "order-123", ...}'
```

**Webhook Callbacks** — Pass `callback_url` to receive async POST notification:

```json
// POST to your callback_url
{
  "event": "certificate.created",
  "data": { "certificate_id": "IF-...", "url": "...", ... }
}
```

**Batch Verification** — Verify up to 100 certificates in one request:

```bash
curl -X POST .../api/certificates/verify \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["token1", "token2"]}'
```

**Bulk Generation** — Admin endpoint to create up to 500 certificates with email delivery:

```bash
curl -X POST .../api/admin/certificates/bulk \
  -H "X-Admin-Key: your-key" \
  -d '{"entries": [{"participant_name": "Alice", "course_name": "...", "participant_email": "alice@example.com"}, ...]}'
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CERT_SECRET_KEY` | **Yes** (prod) | HMAC-SHA256 signing secret |
| `CERT_API_KEYS` | No | Comma-separated API keys for certificate creation |
| `ADMIN_KEY` | No | Admin API authentication key |
| `DATABASE_URL` | No | PostgreSQL connection string (Neon) for analytics & admin |
| `AGENTMAIL_API_KEY` | No | AgentMail API key for email delivery |
| `AGENTMAIL_INBOX_ID` | No | AgentMail inbox (default: `support@intelliforge.tech`) |
| `FOUNDER_NAME` | No | Signature name on certificates (default: `Girish Hiremath`) |
| `FOUNDER_TITLE` | No | Signature title (default: `Founder & CEO, IntelliForge AI`) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7 |
| Backend | FastAPI, Python 3.9+ |
| Database | PostgreSQL (Neon) — optional |
| PDF | xhtml2pdf, ReportLab |
| QR Codes | python-qrcode, Pillow |
| Email | AgentMail |
| Crypto | HMAC-SHA256 (stdlib) |
| Hosting | Vercel (serverless) |

---

## License

MIT
