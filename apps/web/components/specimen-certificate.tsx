import { Eyebrow, Mono } from "@/components/dashboard/ui";

/** The certificate shown on the landing page.
 *
 *  Labelled a specimen, and deliberately so: it carries an ID in the real
 *  `CF-YYYY-XXXXXXXX` shape but one that resolves to nothing. A landing page
 *  that shows a real credential is showing a real person's name and course to
 *  everyone who visits.
 */
export function SpecimenCertificate() {
  return (
    <div className="rounded-xl border border-hair bg-surface p-3.5">
      <div className="rounded-lg border border-hair-soft bg-sunken px-6 py-7">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="font-mono text-[9px] uppercase leading-[1.7] tracking-[0.16em] text-faint">
            Certificate of
            <br />
            completion
          </div>
          <span
            aria-hidden
            className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-lg border border-accent-line bg-accent-wash text-[15px] text-accent"
          >
            ✓
          </span>
        </div>

        <div className="mb-1.5">
          <Eyebrow>Awarded to</Eyebrow>
        </div>
        <div className="mb-4 font-display text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">
          Ananya Rao
        </div>

        <div className="mb-4 h-px bg-hair-soft" />

        <div className="mb-1 text-sm leading-relaxed text-ink">
          Applied AI Engineering — Cohort 07
        </div>
        <div className="mb-6 text-xs text-faint">
          IntelliForge Bootcamp · 12 weeks · 14 Jun 2026
        </div>

        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="mb-1">
              <Eyebrow>Credential ID</Eyebrow>
            </div>
            <Mono className="text-xs text-muted">CF-2026-K7M2P9QX</Mono>
          </div>
          <div
            aria-hidden
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded border border-hair bg-[repeating-linear-gradient(45deg,var(--cf-well)_0_4px,var(--cf-surface-sunken)_4px_8px)] font-mono text-[8px] text-faint"
          >
            QR
          </div>
        </div>
      </div>
    </div>
  );
}
