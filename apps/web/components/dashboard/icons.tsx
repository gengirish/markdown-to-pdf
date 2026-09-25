import type { ReactNode } from "react";

/** The dashboard's handful of icons, inline rather than from a library: seven
 *  glyphs do not justify a dependency. 16px, 1.5px stroke, `currentColor`, so
 *  each takes its colour from the text beside it and follows the theme.
 *  Decorative everywhere they are used — the label next to them is the name. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}

export const OverviewIcon = () => (
  <Icon>
    <rect x="2" y="2" width="5" height="5" rx="1" />
    <rect x="9" y="2" width="5" height="5" rx="1" />
    <rect x="2" y="9" width="5" height="5" rx="1" />
    <rect x="9" y="9" width="5" height="5" rx="1" />
  </Icon>
);

export const IssueIcon = () => (
  <Icon>
    <path d="M8 3v10M3 8h10" />
  </Icon>
);

export const CredentialsIcon = () => (
  <Icon>
    <rect x="2" y="3" width="12" height="10" rx="1.5" />
    <path d="M5 6.5h6M5 9.5h4" />
  </Icon>
);

export const TemplatesIcon = () => (
  <Icon>
    <rect x="2.5" y="2" width="11" height="12" rx="1.5" />
    <path d="M2.5 6h11M6 6v8" />
  </Icon>
);

export const BrandingIcon = () => (
  <Icon>
    <circle cx="8" cy="8" r="6" />
    <circle cx="5.75" cy="6.5" r="0.75" fill="currentColor" stroke="none" />
    <circle cx="9.75" cy="5.5" r="0.75" fill="currentColor" stroke="none" />
    <path d="M8 14a2 2 0 0 1 0-4h2a2 2 0 0 0 2-2" />
  </Icon>
);

export const DevelopersIcon = () => (
  <Icon>
    <path d="M5.5 4.5 2 8l3.5 3.5M10.5 4.5 14 8l-3.5 3.5" />
  </Icon>
);

export const PlanIcon = () => (
  <Icon>
    <path d="M2 13h12M4 13V9M8 13V5M12 13V7" />
  </Icon>
);

export const SettingsIcon = () => (
  <Icon>
    <circle cx="8" cy="8" r="2" />
    <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
  </Icon>
);
