# VTU-style internship completion certificates

IntelliForge certificates are **HMAC-signed, stateless tokens** in the URL: same verification model as course participation certificates, with a dedicated **Forge** PDF/HTML layout for institutional workflows (offer letter → MoU → completion certificate).

## Canonical offer letter (Word)

The repository includes the **VTU internship offer letter** template used with colleges:

- [docs/samples/IntelliForge_Internship_Offer_Letter.docx](samples/IntelliForge_Internship_Offer_Letter.docx)

It is issued under the **VTU Internship Framework** by **Intelliforge Digital Services** (Hyderabad). Placeholders in the letter map naturally to fields you later attest on the completion certificate:

| Offer letter placeholder | Typical certificate / API field |
|--------------------------|-------------------------------|
| `[Full Name of Intern]` | `participant_name` |
| `[USN / Roll Number]` | `usn` |
| `[College Name]` … VTU | `institution_name` |
| `Subject: … Internship at Intelliforge Digital Services` | Align `course_name` with the programme title you register as an active course |
| Start / End / Duration / minimum hours | `completion_date`, `internship_duration`, `internship_hours` |
| Reporting Manager / mentor narrative | `mentor_name` (industry mentor line on the PDF); founder remains **authorised signatory** |

Keep **offer letter reference** (e.g. `Ref: IF/INT/2026/000`) and dates in the Word pack; the digital certificate adds a separate **certificate ID** (`IF-…`) and verification URL for audits.

## API: `POST /api/certificate`

Set `"certificate_kind": "internship"` and provide:

| Field | Token key | Purpose |
|--------|-----------|---------|
| `participant_name` | `n` | Intern / student legal name |
| `course_name` | `c` | Programme or internship title (must be an **active course** on the server) |
| `completion_date` | `d` | Completion / issue date (ISO-style string) |
| `instructor_name` | `i` | Program lead / academic coordinator |
| `usn` | `u` | University Seat Number (VTU) |
| `internship_duration` | `w` | Human-readable window, e.g. `January 2026 – June 2026` |
| `internship_hours` | `h` | Contact / logged hours, e.g. `120` |
| `mentor_name` | `m` | Industry mentor (signature line + QR-backed record) |
| `institution_name` | `s` | Optional college name (included in PDF narrative) |

Participation certificates omit `k` (or use `"certificate_kind": "participation"`) and do not store USN/hours/mentor.

## Verification

- `GET /certificate/{token}/verify` returns `certificate_kind`, and for internships: `usn`, `internship_duration`, `internship_hours`, `mentor_name`, optional `institution_name`.
- `GET /certificate/{token}/download` returns a PDF; internship downloads use filename prefix `Internship_Certificate_`.

## Sample issuance

With the API running:

```bash
python examples/issue_aayush_internship_certificate.py --out ./Aayush_Kulkarni_Internship_Certificate.pdf
```

## Templates (for maintainers)

- PDF HTML: `api/certificate_templates.py` — `CERTIFICATE_INTERNSHIP_VTU_HTML` (Forge letterhead, formal table, three signatures, QR).
- Public viewer: `VIEWER_INTERNSHIP_HTML` in the same module.
- Participation layout: `CERTIFICATE_PARTICIPATION_HTML` (unchanged behaviour for `certificate_kind` participation).

Word (`.docx`) export is not generated server-side; use the PDF for print/share, or convert externally if the college requires Word.
