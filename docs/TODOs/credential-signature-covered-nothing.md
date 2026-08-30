# TODO · `credentials.hmac_signature` asserted an integrity guarantee it did not have

**Opened** 2026-08-30 · **Status** CLOSED — fixed the same day, migration
`b8f3c15d0a72`; not yet deployed · **Severity** high for a credentialing
product, low in blast radius today — the CertForge surface has a handful of
issued credentials and one live org · **Trigger** picking the next work item,
by grepping for readers of every column the model declares

## The finding

Every CertForge credential carries an `hmac_signature`. Grepping the whole
repository for it found:

| Site | What it did |
|---|---|
| `models/credential.py:150` | declared the column, `nullable=False` |
| `migrations/…9b6189514dd3` | created it |
| `services/issuance.py:305` | wrote `hmac_sign(public_id)` |
| `routes/studio.py:109` | wrote `hmac_sign(public_id)` |
| **nothing** | **read it** |

Two writers, no readers. And both signed the public ID alone, so the signature
did not cover the recipient's name, the title, the issue date, the metadata
that renders onto the certificate, or even the issuing organization. Change any
of them directly in the database and the signature still matched, because it
had never seen them.

`/verify/{id}`, `badge.json` and `/credentials/{id}/pdf` all read the row and
rendered it with no check at all. The gate on those routes was `status`, which
answers a different question.

## Why it matters

The product's whole claim is that a credential can be verified. An Open Badge
exported from a tampered row is a machine-readable assertion, under our issuer
ID, vouching for contents we never signed — and the PDF is what gets printed
and handed to an employer.

It also reads as a guarantee in review. The column is named for integrity and
sits next to real signing code, so every reader of `issuance.py` — including
three prior passes over this file — took it for one.

## What it does NOT affect

- **The legacy surface is unaffected and unchanged.** There, the token *is* the
  credential: `_decode_cert` recomputes the HMAC over the whole payload on
  every read, and a mutation invalidates it. That mechanism was always sound.
  This defect was CertForge's DB-backed credentials only.
- No evidence of exploitation, and the exposure needs database write access.
  Anyone holding that could also have inserted a fresh credential outright —
  which is why this ranks as "the guarantee was fictional", not "credentials
  were forged".

## The fix

`api/core/credential_signature.py` — one module that signs and verifies, so
neither half can exist without the other.

- Signs a canonical JSON payload (sorted keys, scheme-and-version prefix) of
  `public_id`, `org_id`, `recipient_name`, `recipient_email`, `title`,
  `issued_at`, `metadata`.
- JSON rather than a delimiter-joined string because the values are
  attacker-supplied: with `name|title`, a recipient named `Alice|Advanced`
  holding the title `Widgetry` signs identically to `Alice` / `Advanced|Widgetry`.
- `credentials.signature_version` records which rule produced a signature.
  `2` is checked; `NULL` means the row predates this and is reported
  `unverified`; anything else fails closed.
- Verified on the viewer, `badge.json`, the PDF route and the v1 JSON verify
  route — all four answer **409**, `error.type = "signature_mismatch"`, rather
  than rendering. `GET /orgs/{slug}/credentials/{id}` reports the status
  instead of refusing: the org is who would investigate, and a 409 there hides
  the row that says which credential is affected.

### Two decisions worth keeping

**Lifecycle columns are not signed.** `status`, `claimed_*`, `revoked_at` and
every `delivery_*` field change by design. A signature covering them would
break the first time someone claimed a credential, and a scheme that
invalidates itself on normal use gets switched off within a week.

**Old rows are not re-signed.** A backfill can only sign what the row says
today, so it would manufacture exactly the evidence it claims to verify.
`unverified` is the honest answer, and it is the same rule
`delivery_status = "unknown"` follows for rows that predate delivery state.

## Why the existing tests missed it

The same shape as the four incidents in `CLAUDE.md`: **two halves each correct
in isolation, with nothing testing the join.** `hmac_sign` / `hmac_verify` have
their own passing tests in `test_crypto.py` and are correct. The viewer, badge
and PDF routes have passing tests and render correctly. No test ever asked
whether the thing that writes the signature and the thing that reads it are
connected — because nothing read it, there was no join to test, and its absence
looked exactly like coverage.

The general form: **a column with writers and no readers is not a feature, it
is a claim.** Grepping the model for fields nothing reads back is worth doing
periodically; this one had survived three reviews.

`tests/test_credential_signature.py` closes it, and every guard in it was
verified by reintroducing the defect on purpose — ten mutations, each watched
for the specific test that catches it: the id-only signature, verification
removed from `_get_credential_data`, from `badge.json`/`pdf`, the worker's
re-sign dropped, bulk staging's sign dropped, a delimiter-joined payload, naive
datetimes left unnormalised, `NULL` treated as valid, an unknown version
treated as valid, and a field silently dropped from the signed payload while
staying listed in `covers`.

## Still open

- **Not deployed.** The migration adds a nullable column and runs in
  `release_command`; nothing needs backfilling.
- The dashboard does not surface `signature.status`. `GET
  /orgs/{slug}/credentials/{id}` returns it, and an org with a tampered row
  currently learns about it only through the API.
- Credentials issued before this change will report `unverified` forever. That
  is intended, but it means the first customer-visible "verified" badge should
  not claim more than the column supports.
