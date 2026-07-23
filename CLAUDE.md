# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

API-first generator for tamper-proof PDF certificates (participation, VTU internship, event appreciation) and tax invoices. Certificate data lives entirely inside an HMAC-SHA256-signed URL token — no database is needed to issue, view, or verify a document. FastAPI backend on Vercel Functions + React/Vite frontend.

## Commands

```bash
# Setup
npm install && pip install -r requirements.txt

# Dev (two terminals) — Vite proxies /api, /certificate, /invoice to :8000
python -m uvicorn api.index:app --reload --port 8000
npm run dev                       # http://localhost:5173

npm run build                     # vite build -> dist/
npm run lint                      # eslint (JS/JSX only)
ruff check api/ sdk/pdfcert/      # Python lint used in CI

# Tests — all require the API running on :8000
python test_api.py                # integration suite, prints pass/fail per case
python sdk/test_sdk.py            # SDK suite (PDFCERT_URL overrides base URL)
npm run test:e2e                  # Playwright; auto-starts uvicorn + vite itself
npm run test:e2e:ui               # single spec / interactive picker
E2E_BASE_URL=https://... npm run test:e2e   # run e2e against a deployed URL
```

`test_api.py` and `sdk/test_sdk.py` are plain scripts, not pytest — there is no per-test selector; comment out entries in `run_all()` / `__main__` to narrow a run.

## Architecture

### Stateless signed tokens (the core idea)

`api/index.py` `_encode_cert` / `_decode_cert`: the payload is compact JSON → urlsafe base64 → `payload.hmac_sha256_hex`. Verification recomputes the HMAC with `CERT_SECRET_KEY`; any mutation invalidates the token. Consequences to keep in mind:

- **Token keys are single letters** (`n` name, `c` course, `d` date, `i` instructor, `k` kind, `u` USN, `w` duration, `h` hours, `m` mentor, `s` institution, `r` recognition, `e` event, `v` venue, `p` sponsor). Renaming or reordering a key breaks every previously issued certificate. Add new fields as new optional keys only.
- **`k` selects the document kind**: absent/`participation`, `i` internship, `a` appreciation. `_certificate_kind_from_payload` is the dispatch point; nearly every render path branches on it.
- Changing `CERT_SECRET_KEY` invalidates all outstanding certificates.
- Invoices use the same scheme with their own compaction helpers (`compact_invoice_token_payload` / `expand_invoice_token_payload` in `api/invoice_utils.py`).

### Database is optional

`api/db.py` is only loaded when `DATABASE_URL` is set (`DB_AVAILABLE` / `_ensure_db_ready()`). Without it: courses fall back to the hardcoded `COURSES_FALLBACK` list in `api/index.py`, admin endpoints 503, and revocation is a no-op. Verification never touches the DB. Any new feature must degrade gracefully when the DB is absent.

### Rendering: three surfaces per document kind

Each document kind is rendered three separate times and these must be kept visually in sync when changing a layout:

1. **PDF** — HTML string templates in `api/certificate_templates.py` (`CERTIFICATE_PARTICIPATION_HTML`, `CERTIFICATE_INTERNSHIP_VTU_HTML`, `CERTIFICATE_APPRECIATION_HTML`) and `api/invoice_templates.py`, rendered by xhtml2pdf via `_build_cert_pdf` / `build_invoice_pdf`. xhtml2pdf supports only a narrow CSS subset — tables and inline styles, no flex/grid; images must be base64 data URIs (see `_generate_qr_data_uri`, `_generate_signature_data_uri`, `api/appreciation_assets.py`).
2. **Public viewer HTML** — `VIEWER_HTML` in `api/index.py`, `VIEWER_INTERNSHIP_HTML` / `VIEWER_APPRECIATION_HTML` in `api/certificate_templates.py`.
3. **Live React preview** — `CertificatePreviewCard` / `InvoicePreviewCard` in `src/App.jsx`, which duplicate the layout in real CSS.

Shared logic that all three depend on (signatory dedup, host-name resolution) exists in both Python and JS: `_norm_signatory` / `_unique_signatory_roles` / `resolve_appreciation_host_name` in Python have JS twins in `src/App.jsx`. Change both.

### Branding flows from env → `/api/info` → frontend

Branding is env-driven (`CERT_*`, `FOUNDER_*`, `INVOICE_*` vars; see README table). `certificate_branding()` and `invoice_brand_colors()` (`api/invoice_brand.py`) serialize it, `/api/info` exposes it, and the `useBranding` / `useInvoiceBrand` hooks in `src/App.jsx` consume it. Never hardcode brand strings or colors in templates — add an env-backed key instead. All env reads go through `_sanitize_env`.

### Single-function deploy

`vercel.json` rewrites `/api/*`, `/certificate/*`, `/invoice/*`, `/docs`, `/openapi.json`, `/llms.txt`, `/sitemap.xml`, `/robots.txt`, `/.well-known/*` to the one Python function `api/index.py`; everything else falls through to the SPA. New backend routes must be added to the rewrite list or they will 404 in production while working locally.

### Cross-cutting request behavior

Applied inside `POST /api/certificate` and `/api/invoice` handlers, not as middleware: in-memory rate limiting (`_check_rate_limit`, 10/60s per IP), in-memory idempotency cache (`_check_idempotency`, 1h TTL), `X-API-Key` auth bypassed for same-origin browser requests (`_is_browser_same_origin`), fire-and-forget webhooks (`_fire_webhook`), and optional AgentMail delivery. **Both in-memory caches are per-instance** and do not survive serverless cold starts — treat them as best-effort.

Admin endpoints require `X-Admin-Key` via `_require_admin` plus `_require_db`.

## Agent-discovery surface

`/llms.txt`, `/robots.txt`, `/sitemap.xml`, `/.well-known/ai-plugin.json`, and JSON-LD injected into viewer pages are generated in `api/index.py` (`_build_llms_txt`, `_participation_json_ld`, `_internship_json_ld`). Adding a public endpoint means updating `_build_llms_txt` and `_build_sitemap_xml` too.

## Related

- `sdk/` — installable Python client (`cd sdk && pip install -e .`), tested against a live server.
- `examples/` — runnable scripts for bulk onboarding, batch verify, webhooks, Zapier.
- `docs/certificate-internship-vtu.md` — internship field ↔ token-key mapping and college workflow.
