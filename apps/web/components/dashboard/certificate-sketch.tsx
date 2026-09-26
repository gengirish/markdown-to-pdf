"use client";

import type { CSSProperties, ReactNode } from "react";

import type { TemplateConfig } from "@/lib/api";
import { LAYOUT_WORDING } from "@/lib/template-presets";

/** A live, in-browser sketch of the guided certificate.
 *
 *  It exists so an author can see what a field does while typing it — "Footer
 *  line" meant nothing until you could see the band it prints in. It redraws on
 *  every keystroke, which the real preview (a server-rendered PDF in a new tab)
 *  cannot.
 *
 *  It is a *third copy* of the guided layout — TEMPLATE_SHELL in
 *  apps/api/api/services/templates.py is the source, the PDF the second — so it
 *  says it is a sketch, and "Preview PDF" stays beside it as the final word.
 *  Change the shell's structure and change this too. The fallbacks mirror
 *  `build_render_variables` in apps/api/api/services/rendering.py.
 *
 *  The hex literals below are the *document's* colours, not the dashboard's.
 *  Paper does not follow the theme, so these deliberately do not use tokens;
 *  the highlight and callouts around the page do.
 */

export type SketchPart =
  | "logo"
  | "issuer"
  | "heading"
  | "body"
  | "name"
  | "closing"
  | "title"
  | "date"
  | "signature"
  | "qr"
  | "footer";

const FALLBACK_PRIMARY = "#1e293b";
const FALLBACK_ACCENT = "#d4af37";
const FALLBACK_FOOTER = "Powered by CertForge · certforge.intelliforge.tech";
const HEX = /^#[0-9a-fA-F]{6}$/;

const DISPLAY = '"EB Garamond", Garamond, Georgia, "Times New Roman", serif';

/** What each numbered callout is, and where it is set. Order is page order. */
const LEGEND: { part: SketchPart; label: string; where: string }[] = [
  { part: "logo", label: "Logo", where: "Branding" },
  { part: "issuer", label: "Organization name", where: "your organization" },
  { part: "heading", label: "Heading", where: "Template" },
  { part: "body", label: "Opening line", where: "Template" },
  { part: "name", label: "Recipient name", where: "each credential" },
  { part: "closing", label: "Line before the title", where: "Template" },
  { part: "title", label: "Title / course", where: "each credential" },
  { part: "date", label: "Date and credential ID", where: "automatic" },
  { part: "signature", label: "Signature", where: "Template" },
  { part: "qr", label: "Verification QR code", where: "automatic" },
  { part: "footer", label: "Footer line", where: "Branding" },
];

const DEFAULT_GUIDED: TemplateConfig = {
  layout: "participation",
  ...LAYOUT_WORDING.participation,
  signature_name: "",
  signature_title: "",
  show_qr: true,
  show_logo: true,
  show_footer: true,
};

/** Points on the A4-landscape page (842pt wide) → a length that scales with the
 *  sketch's width, so it is the same drawing at any size. */
const pt = (n: number) => `calc(${n} * 100cqw / 842)`;

export function CertificateSketch({
  issuerName,
  primaryColor,
  accentColor,
  footerText,
  logoSrc,
  config = DEFAULT_GUIDED,
  highlight = null,
  annotate = true,
  caption,
}: {
  issuerName: string;
  primaryColor: string;
  accentColor: string;
  footerText: string;
  /** The uploaded logo's URL, or null when there is none. */
  logoSrc: string | null;
  config?: TemplateConfig;
  highlight?: SketchPart | null;
  annotate?: boolean;
  caption?: ReactNode;
}) {
  const primary = HEX.test(primaryColor) ? primaryColor : FALLBACK_PRIMARY;
  const accent = HEX.test(accentColor) ? accentColor : FALLBACK_ACCENT;
  const footer = footerText.trim() || FALLBACK_FOOTER;
  const hasSignature = config.signature_name.trim() !== "";

  // Numbered in page order, over only the parts this configuration prints.
  const shown = LEGEND.filter(({ part }) => {
    if (part === "logo") return config.show_logo;
    if (part === "qr") return config.show_qr;
    if (part === "footer") return config.show_footer;
    if (part === "signature") return hasSignature;
    return true;
  });
  const number = (part: SketchPart) => shown.findIndex((entry) => entry.part === part) + 1;

  const mark = (part: SketchPart, children: ReactNode, style?: CSSProperties) => (
    <Marked
      part={part}
      n={annotate ? number(part) : 0}
      active={highlight === part}
      style={style}
    >
      {children}
    </Marked>
  );

  return (
    <figure className="m-0">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
          Live sketch · sample recipient
        </span>
        <span className="text-xs text-faint">Preview PDF shows the exact render</span>
      </div>

      <div
        aria-hidden
        className="overflow-hidden rounded-lg border border-hair"
        style={{ containerType: "inline-size" }}
      >
        <div
          style={{
            background: "#0f0f23",
            padding: `${pt(24)} ${pt(32)}`,
            fontFamily: "Helvetica, Arial, sans-serif",
            color: "#2d3748",
            lineHeight: 1.25,
          }}
        >
          <div style={{ background: "#ffffff" }}>
            {/* Header band */}
            <div style={{ background: primary, padding: `${pt(30)} ${pt(40)} ${pt(26)}`, textAlign: "center" }}>
              {config.show_logo
                ? mark(
                    "logo",
                    logoSrc ? (
                      // Exact bytes the certificate embeds, from the API host.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={logoSrc} alt="" style={{ height: pt(30), display: "inline-block" }} />
                    ) : (
                      <span
                        style={{
                          display: "inline-block",
                          border: "1px dashed rgba(255,255,255,0.55)",
                          color: "rgba(255,255,255,0.8)",
                          fontSize: pt(8),
                          padding: `${pt(6)} ${pt(12)}`,
                        }}
                      >
                        No logo uploaded — nothing prints here
                      </span>
                    ),
                    { paddingBottom: pt(8) },
                  )
                : null}
              {mark(
                "issuer",
                <span style={{ fontSize: pt(25), fontWeight: 700, color: "#ffffff", fontFamily: DISPLAY }}>
                  {issuerName || "Your organization"}
                </span>,
                { padding: `${pt(6)} 0 ${pt(12)}` },
              )}
              {mark(
                "heading",
                <span
                  style={{
                    display: "inline-block",
                    border: `2px solid ${accent}`,
                    padding: `${pt(6)} ${pt(30)}`,
                    fontSize: pt(9),
                    letterSpacing: pt(3),
                    color: accent,
                    fontWeight: 700,
                  }}
                >
                  {config.heading || " "}
                </span>,
              )}
            </div>

            {/* Body */}
            <div style={{ padding: `${pt(28)} ${pt(50)} ${pt(20)}`, textAlign: "center" }}>
              <div style={{ paddingBottom: pt(18) }}>
                <span
                  style={{
                    display: "inline-block",
                    border: "1px solid #68d391",
                    background: "#f0fff4",
                    color: "#276749",
                    fontWeight: 700,
                    fontSize: pt(8),
                    padding: `${pt(4)} ${pt(14)}`,
                  }}
                >
                  ✓ &nbsp; Verified &amp; Authentic
                </span>
              </div>
              {mark(
                "body",
                <span style={{ fontSize: pt(8), letterSpacing: pt(3), color: "#a0aec0" }}>
                  {config.body.toUpperCase() || " "}
                </span>,
                { paddingBottom: pt(6) },
              )}
              {mark(
                "name",
                <span style={{ fontSize: pt(34), fontWeight: 700, color: "#1a202c", fontFamily: DISPLAY }}>
                  Ananya Rao
                </span>,
                { padding: `${pt(4)} 0 ${pt(2)}` },
              )}
              <div style={{ width: "60%", margin: "0 auto", borderTop: "2px solid #d4af37" }} />
              {mark(
                "closing",
                <span style={{ fontSize: pt(9), color: "#718096" }}>{config.closing || " "}</span>,
                { paddingTop: pt(12) },
              )}
              {mark(
                "title",
                <span style={{ fontSize: pt(16), fontWeight: 700, color: "#553c9a", fontFamily: DISPLAY }}>
                  Applied AI Engineering — Cohort 07
                </span>,
                { padding: `${pt(4)} 0 ${pt(20)}` },
              )}
              {config.layout === "internship" ? (
                <div style={{ fontSize: pt(10), color: "#4a5568", paddingBottom: pt(14) }}>
                  USN 1XX22CS001 &nbsp;·&nbsp; 12 weeks
                </div>
              ) : null}
              {mark(
                "date",
                <div
                  style={{
                    width: "85%",
                    margin: "0 auto",
                    display: "flex",
                    borderTop: "1px solid #edf2f7",
                    borderBottom: "1px solid #edf2f7",
                  }}
                >
                  <PanelCell value="26 Sep 2026" label="DATE" />
                  <PanelCell value="CF-2026-K7M2P9QX" label="CREDENTIAL ID" divided />
                </div>,
              )}
              {hasSignature
                ? mark(
                    "signature",
                    <div style={{ width: pt(230), margin: "0 auto" }}>
                      <div style={{ fontSize: pt(17), color: "#1a202c", fontFamily: DISPLAY, paddingBottom: pt(2) }}>
                        {config.signature_name}
                      </div>
                      <div style={{ borderTop: "1px solid #cbd5e0" }} />
                      <div style={{ fontSize: pt(7), letterSpacing: pt(1), color: "#a0aec0", paddingTop: pt(4) }}>
                        {config.signature_title.toUpperCase()}
                      </div>
                    </div>,
                    { paddingTop: pt(22) },
                  )
                : null}
              {config.show_qr
                ? mark(
                    "qr",
                    <div style={{ display: "inline-flex", alignItems: "center", gap: pt(12), textAlign: "left" }}>
                      <span
                        style={{
                          width: pt(70),
                          height: pt(70),
                          flexShrink: 0,
                          background:
                            "repeating-conic-gradient(#1a202c 0 25%, #ffffff 0 50%) 0 0 / 20% 20%",
                          border: `${pt(4)} solid #ffffff`,
                          outline: "1px solid #e2e8f0",
                        }}
                      />
                      <span>
                        <span style={{ display: "block", fontSize: pt(9), fontWeight: 700, color: "#2d3748" }}>
                          Scan to Verify
                        </span>
                        <span style={{ display: "block", fontSize: pt(7), color: "#a0aec0" }}>
                          Links to this certificate&rsquo;s permanent verification page.
                        </span>
                      </span>
                    </div>,
                    { paddingTop: pt(16) },
                  )
                : null}
            </div>

            {config.show_footer
              ? mark(
                  "footer",
                  <span style={{ fontSize: pt(7), color: "#a0aec0" }}>{footer}</span>,
                  {
                    background: "#f8fafc",
                    borderTop: "1px solid #edf2f7",
                    padding: `${pt(10)} ${pt(40)}`,
                    textAlign: "center",
                  },
                )
              : null}
          </div>
        </div>
      </div>

      {annotate ? (
        <figcaption className="mt-3">
          <ol className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-muted sm:grid-cols-2">
            {shown.map((entry, index) => (
              <li
                key={entry.part}
                className={`flex items-baseline gap-2 rounded px-1 ${
                  highlight === entry.part ? "bg-accent-wash text-ink" : ""
                }`}
              >
                <span className="font-mono text-[10px] text-accent">{index + 1}</span>
                <span>
                  {entry.label} <span className="text-faint">· {entry.where}</span>
                </span>
              </li>
            ))}
          </ol>
          {caption ? <div className="mt-2 text-xs text-faint">{caption}</div> : null}
        </figcaption>
      ) : null}
    </figure>
  );
}

function PanelCell({ value, label, divided = false }: { value: string; label: string; divided?: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        padding: `${pt(12)} ${pt(8)}`,
        borderLeft: divided ? "1px solid #edf2f7" : undefined,
      }}
    >
      <div style={{ fontSize: pt(11), fontWeight: 700, color: "#2d3748" }}>{value}</div>
      <div style={{ fontSize: pt(6), letterSpacing: pt(2), color: "#a0aec0", paddingTop: pt(3) }}>{label}</div>
    </div>
  );
}

/** One named region of the page: a numbered callout, and an outline while the
 *  field that sets it has focus. */
function Marked({
  part,
  n,
  active,
  style,
  children,
}: {
  part: SketchPart;
  n: number;
  active: boolean;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <div
      data-part={part}
      style={{
        position: "relative",
        outline: active ? "2px solid var(--cf-accent)" : "2px solid transparent",
        outlineOffset: pt(3),
        transition: "outline-color 120ms",
        ...style,
      }}
    >
      {children}
      {n > 0 ? (
        <span
          style={{
            position: "absolute",
            top: "50%",
            left: pt(8),
            transform: "translateY(-50%)",
            // A pill rather than a circle, so "10" and "11" fit.
            minWidth: "max(14px, calc(16 * 100cqw / 842))",
            height: "max(14px, calc(16 * 100cqw / 842))",
            padding: "0 3px",
            boxSizing: "border-box",
            borderRadius: "999px",
            background: "var(--cf-accent)",
            color: "var(--cf-ground)",
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "max(9px, calc(8 * 100cqw / 842))",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            lineHeight: 1,
          }}
        >
          {n}
        </span>
      ) : null}
    </div>
  );
}
