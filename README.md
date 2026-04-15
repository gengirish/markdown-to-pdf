# IntelliForge Certificates

**API-first verifiable credentials with zero database, zero vendor lock-in.**

Generate tamper-proof participation certificates with shareable URLs. All certificate data lives inside the URL itself — signed with HMAC-SHA256, no database required.

---

## How It Works

```
1. POST /api/certificate        → Returns a signed token URL
2. GET  /certificate/{token}    → Public viewer page (HTML)
3. GET  /certificate/{token}/download → PDF with embedded QR
4. GET  /certificate/{token}/verify   → JSON verification
```

The token encodes participant name, course, date, and instructor as a base64 payload with a full HMAC-SHA256 signature appended. Any tampering invalidates the signature, making certificates cryptographically verifiable without a database.

### Architecture

```
┌─────────────────┐          ┌─────────────────────────────────┐
│  React Frontend │  ──────► │  FastAPI Backend (Vercel)        │
│  (Vite)         │  POST    │                                  │
│                 │  ◄────── │  HMAC-SHA256 token engine        │
│  - Form input   │  JSON    │  xhtml2pdf (PDF renderer)        │
│  - Live preview │          │  python-qrcode (self-hosted QR)  │
│  - Social share │          │  Rate limiter + API key auth     │
└─────────────────┘          └─────────────────────────────────┘
                                        │
                              ┌─────────┴──────────┐
                              ▼                    ▼
                     Public Viewer Page      PDF Download
                     (social meta tags,     (matching design,
                      QR code, share)       embedded QR code)
```

### What makes this different

- **Stateless** — No database, no Redis, no S3. Certificates live in the URL.
- **Tamper-proof** — HMAC-SHA256 signature; any modification is detected.
- **Privacy-first** — QR codes rendered server-side, no third-party calls.
- **Serverless-native** — Runs on Vercel Functions with zero cold-start state.
- **Viral loop** — Every certificate shared on LinkedIn links back to your platform.

---

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.9+ and pip

### Install

```bash
npm install
pip install -r requirements.txt
```

### Run locally (two terminals)

```bash
# Terminal 1 — Backend
python -m uvicorn api.index:app --reload --port 8000

# Terminal 2 — Frontend
npm run dev
```

Open **http://localhost:5173**

### Run tests

```bash
# Start the backend first, then:
python test_api.py
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check with version |
| `GET` | `/api/health` | Service health |
| `GET` | `/api/info` | API metadata |
| `GET` | `/api/courses` | List available courses |
| `POST` | `/api/convert` | Markdown → PDF conversion |
| `POST` | `/api/certificate` | Create a signed certificate |
| `GET` | `/certificate/{token}` | Public certificate viewer |
| `GET` | `/certificate/{token}/download` | Download certificate PDF |
| `GET` | `/certificate/{token}/verify` | Verify certificate authenticity |

### Create a certificate

```bash
curl -X POST https://your-app.vercel.app/api/certificate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "participant_name": "Jane Doe",
    "course_name": "AI Code Reviewer Course",
    "completion_date": "2026-04-15",
    "instructor_name": "IntelliForge AI Team"
  }'
```

Response:

```json
{
  "certificate_id": "IF-A1B2C3D4E5F6",
  "token": "eyJjIjoi...",
  "url": "https://your-app.vercel.app/certificate/eyJjIjoi...",
  "download_url": "https://your-app.vercel.app/certificate/eyJjIjoi.../download",
  "participant_name": "Jane Doe",
  "course_name": "AI Code Reviewer Course"
}
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CERT_SECRET_KEY` | **Yes** (prod) | HMAC-SHA256 signing secret. Must be set in production. |
| `CERT_API_KEYS` | No | Comma-separated API keys for `POST /api/certificate`. If unset, auth is disabled. |

---

## Deployment (Vercel)

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel --prod
```

Set environment variables in Vercel project settings:

```
CERT_SECRET_KEY=<a-strong-random-secret>
CERT_API_KEYS=key1,key2
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7, marked |
| Backend | FastAPI, Python 3.9+ |
| PDF | xhtml2pdf, ReportLab |
| QR Codes | python-qrcode, Pillow |
| Crypto | HMAC-SHA256 (stdlib) |
| Hosting | Vercel (serverless) |

---

## License

MIT
