# DIKW Inversion: Certificates

2026-09-21

A problem-discovery exercise using the DIKW Inversion framework (Data, Information,
Knowledge, Wisdom). It asks whether certificates could stop being a recurring chore,
not just get faster to make.

## 1. The situation

After every workshop, internship batch or hackathon, one coordinator loses an evening
in Canva making certificates, exporting them and emailing them one at a time, and some
names still go out misspelled. Weeks later an HR team or a college office asks "did you
really issue this?", and someone has to dig through old folders to answer, because a
PDF can be edited in two minutes and proves nothing by itself.

## 2. The DIKW ladder

**Data:** Indian background-check firms such as AuthBridge publish yearly reports on
how many job candidates have a false or mismatched credential. Figures around 1 in 10
are often quoted, but check the current report before using a number.

**Information:** There are plenty of how-to guides: Canva "bulk create" and Word
mail-merge tutorials, Google Sheets add-ons that email a PDF to each row, and
comparison articles on tools like Certifier, Accredible and CertifyMe.

**Knowledge:** Registrars and HR people already know good practice: a unique
certificate ID with a QR code, a central issue register, sending only from an official
domain, and calling the issuer when in doubt.

## 3. Reality restoration

All of this makes the old routine faster and a bit safer: making certificates takes
minutes, and checking one takes a scan instead of a phone call. But the certificate is
still a file made after the event, typed by someone else and held by the recipient, so
the issuer still gets pulled back in whenever someone doubts it.

## 4. Wisdom

Wisdom asks why proof that someone attended or completed something has to be turned
into a separate file after the fact, typed by a busy coordinator, carried around by the
recipient, and trusted only after the issuer is tracked down and asked.

## 5. Reality transcendence

The record comes into being at the moment it happens. When an attendee checks in, or a
mentor signs off an intern's last week, that act is the credential: the attendee typed
their own name, and nobody makes anything afterwards.

The record stays with whoever issued it. A recruiter or placement cell checks it there
directly, the way you check a train PNR, so "did you really issue this?" goes unasked.

People can still get a PDF, but it becomes a printout of the record, not the proof.

## 6. Opportunities in the wisdom economy

Opportunities 1 and 3 are where the old job starts to disappear. The current product
(bulk CSV issuance plus QR verification) mostly sits in reality restoration: it does
the old job much better.

| Opportunity | Reality shift | Type | How it earns | What exists, and what's still unsolved |
| --- | --- | --- | --- | --- |
| 1. Check-in that issues the credential | Attendees scan a QR or sign in, typing their own name. When the organizer closes the event, credentials go out with no list to prepare. | Product + Process | Per-event or per-attendee price for organizers and colleges | Certifier, Accredible, CertifyMe and the CSV flow all start after the event from a typed list, so the after-event work and misspellings remain |
| 2. Mentor sign-off for internships | The host company's mentor approves completion in a record the college exam cell reads directly. A VTU internship certificate becomes a lookup. | Service + Process | Colleges pay per batch, or high-volume host companies pay yearly | The AICTE internship portal lists internships but, as far as known, does not confirm completion (verify this). Colleges still collect signed PDFs |
| 3. A lookup desk for verifiers | Recruiters and background-check firms check any credential in one place by ID or name plus issuer. The issuer never gets an email. | Product | Per-check fee or API subscription for background-check firms; free for issuers | DigiLocker and the National Academic Depository cover university degrees, not workshops, bootcamps or internships. Those checks are still email and phone |
| 4. A recipient profile only issuers can add to | Students share one link instead of attaching PDFs, and nothing appears unless an issuer put it there. | Product | Free for students; pulls in issuers and gives recruiters a reason to trust the link | LinkedIn certifications are self-reported, and Credly is thin in Indian colleges. Recruiters still can't tell which entries are real |

## 7. The smallest version to test in 21 days

Test opportunity 1, the check-in that issues credentials, with a verifier check added
at the end. It succeeds if organizers do nothing after the event and recruiters never
feel the need to contact the issuer.

- **What to set up:** For each event, a Google Form or QR sign-in page where attendees
  type their own name and email. When the organizer closes it, the existing system
  issues credentials automatically.
- **Who:** 5 real organizers (college departments, a coding club, a hackathon), plus 5
  HR recruiters or placement officers. Show each recruiter 10 certificates from those
  events, 3 of them edited.
- **Measure for organizers:** minutes spent after the event and the number of
  misspelled names. Aim for close to zero on both.
- **Measure for recruiters:** how many use the link instead of emailing to confirm, and
  how many of the edited ones they catch.

## 8. Problem statement

"How might we help event organizers, colleges and the recruiters who check their
certificates move from making certificates by hand after every event and answering
'did you really issue this?' weeks later, to a world where the credential is created at
the moment of attendance and anyone can check it at the source without asking, starting
with a QR check-in that issues credentials automatically, tested with 5 organizers and
5 recruiters over 21 days?"
