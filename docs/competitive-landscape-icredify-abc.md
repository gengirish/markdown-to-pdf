---
title: Competitive landscape — iCredify and ABC/APAAR vs CertForge
date: 2026-11-11
sources:
  - https://www.icredify.com/ (snapshot: docs/icredify.md)
  - https://www.abc.gov.in/ (home page, fetched 2026-11-11)
---

# Competitive landscape: iCredify and ABC vs CertForge

## The three players

### ABC — Academic Bank of Credits (Government of India)

- Flagship initiative of the **Ministry of Education**, regulated by **UGC**; platform
  built and run by **Digital India Corporation (MeitY)**.
- A "credit bank": academic credits from recognised institutions are stored,
  accumulated, transferred across institutions and redeemed, aligned to the
  **National Credit Framework (NCrF)**.
- Keyed on **APAAR ID** ("One Nation, One Student ID") — a lifelong, Aadhaar-linked
  learner ID. ABC cannot be used without one. School students get it via UDISE
  against their PEN ID; higher-ed learners create it through DigiLocker.
- Part of one public stack with **DigiLocker** and **NAD (National Academic
  Depository)** — universities ("awarding institutions") upload degrees and marks to
  NAD; students hold them in DigiLocker.
- Only award-granting bodies recognised by MoE, UGC, AICTE, NCVET or another competent
  regulator may register.
- Claims on the home page: **1.90 Cr** students with credit awards seeded with APAAR
  ID; **5.45 Cr** academic records mapped. Promises "universities and employers can
  instantly verify a student's credentials."

### iCredify (iCrederity Info Services Pvt. Ltd., Bangalore)

- Education background-verification service, founded 2014.
- Verifies **degree certificates and marks cards** after the fact.
- Universities join free and answer verification requests through its portal
  (testimonial: JNTU Ananthapur); corporates/HR pay to check candidates; students can
  get their own qualifications verified.
- Sales-led B2B, part of the wider background-verification (BGV) industry. Its moat is
  the university network and employer trust.

### CertForge (this repo)

- **Issues** verifiable credentials. Legacy surface: HMAC-signed stateless tokens with
  QR codes (participation, VTU internship, appreciation, invoices). CertForge surface:
  multi-tenant orgs, templates incl. traced artwork, bulk CSV issuance, delivery
  tracking, verify pages, Open Badges 3.0, passports/claims, API keys, webhooks.
- Self-serve SaaS + API. Community free (50/month), Pro ₹1,999 (1,000/month).

## Side by side

| | **ABC + APAAR + NAD** (Govt) | **iCredify** (private) | **CertForge** (us) |
|---|---|---|---|
| What it is | National registry of degrees, marks, credits | Paid verification-after-the-fact service | SaaS for **issuing** verifiable certificates |
| Source of truth | University uploads to NAD/DigiLocker | University confirms via iCredify's portal | Issuer's cryptographic signature (HMAC) |
| Who can issue | Only recognised degree-granting bodies | Doesn't issue | Any org — bootcamps, companies, events, colleges |
| Documents | Degrees, marks cards, credits | Degrees, marks cards | Participation, internship, appreciation, course certs, Open Badges |
| Identity | Aadhaar-linked APAAR ID | — | Recipient email, claim link, passport |
| Cost | Free (public infrastructure) | Paid per check | Free tier, then ₹1,999/month |
| Verification | DigiLocker lookup (consent/login) | Slow, human-mediated | Instant QR/URL scan, public, no login |
| Distribution | Mandated top-down, every Indian student eventually | Sales-led university/corporate network | Self-serve + API |

## Implications for CertForge

1. **ABC threatens iCredify, not us.** As NAD fills up, checking a degree becomes a
   free DigiLocker lookup, which erodes iCredify's core business.
2. **ABC only covers formal, regulator-recognised credentials.** Bootcamp
   certificates, internships, hackathons, workshops, corporate training and event
   participation largely fall outside it. That is CertForge's market.
3. **The VTU internship certificate is the boundary case.** If an internship earns
   credit, the *credit* lands in ABC via the university; the *certificate* the host
   organisation issues stays outside. CertForge is the input to ABC, not a rival.
4. **Do not collect APAAR IDs.** It was considered (as an optional legacy token
   key, or in v1 `metadata`) and rejected:
   - **A legacy token is readable by anyone.** Its payload is base64 JSON, not
     encrypted, and it sits in the URL and QR code. An APAAR ID put there would be
     printed in recoverable form on paper that can never be reissued. The freeze
     contract allowing a new optional key does not make this one acceptable.
   - **v1 `metadata` is public too.** The unauthenticated verify route returns it
     (`routes/verify.py`) and it feeds the PDF variables. Storing it safely would
     need a separate access-controlled column, plus DPDP Act duties: consent,
     purpose, retention, breach notification.
   - **CertForge cannot upload to NAD.** Only registered institutions do, and only
     credit-bearing records from recognised bodies. Event and appreciation
     certificates are out of scope, and VTU internship credit is awarded by VTU.
   - **The institution already has the APAAR ID.** It maps its own students to
     APAAR. For VTU, the USN (`u`) is the join key the college matches on its side.
5. **If a bridge is wanted, make it an export.** Give an institution a list of its
   issued internship credentials keyed by USN. It does the APAAR match and the NAD
   upload. CertForge holds no new identifier. Do not market this as "ABC-ready"
   until one institution has actually moved a CertForge credential into NAD. The
   positioning that is true today: "covers the credentials ABC doesn't".

## Open questions

Answer these, ideally with a college that uploads to NAD, before building the export
in point 5:

- NAD upload mechanics for awarding institutions (format, API vs bulk upload, whether
  non-degree certificates are accepted). Only ABC's home page was read.
- Whether a private issuer may collect and store APAAR IDs, and under what consent
  terms. This decides whether point 4 is ever revisited. Until it is answered, the
  answer is no.
