import { useState, useEffect, useId } from 'react'
import './App.css'

function CertIcon({ size = 32 }) {
  const id = useId()
  const gradId = `if-grad-${id}`
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="40" height="40" rx="10" fill={`url(#${gradId})`} />
      <path d="M12 12h4v16h-4V12z" fill="white" opacity="0.9" />
      <path d="M20 12h4v16h-4V12z" fill="white" opacity="0.7" />
      <path d="M28 12v4h-8v2h6v4h-6v2h8v4H20V12h8z" fill="white" opacity="0.9" />
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366F1" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
    </svg>
  )
}

const Icon = {
  Download: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  ),
  Loader: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="icon-spin">
      <line x1="12" y1="2" x2="12" y2="6" />
      <line x1="12" y1="18" x2="12" y2="22" />
      <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
      <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
      <line x1="2" y1="12" x2="6" y2="12" />
      <line x1="18" y1="12" x2="22" y2="12" />
      <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
      <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
    </svg>
  ),
  Award: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="7" />
      <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
    </svg>
  ),
  ExternalLink: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  ),
  Copy: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  Check: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  CheckCircle: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  CertTab: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="7" />
      <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
    </svg>
  ),
  Admin: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  ),
  Invoice: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  ),
}

const PREVIEW_CERT_URL = '/certificate/preview'

function useBranding(getApiUrl) {
  const [branding, setBranding] = useState({
    org_tagline: 'AN INTELLIFORGE AI INITIATIVE',
    brand_name: 'IntelliForge Learning',
    participation_title: 'Certificate of Participation',
    issued_by: 'IntelliForge Learning',
    website: 'learning.intelliforge.tech',
    internship_org: 'Intelliforge Digital Services',
    internship_brand_prefix: 'IntelliForge',
    appreciation_org: 'IntelliForge AI',
    appreciation_org_bold: 'IntelliForge',
    appreciation_org_light: 'AI',
    appreciation_partner_org: 'maidaan.academy',
    appreciation_title_line1: 'CERTIFICATE',
    appreciation_title_line2: 'OF APPRECIATION',
    appreciation_presented_label: 'This certificate is proudly presented to',
    appreciation_accent: '#F05B00',
    appreciation_sidebar_color: '#0A2818',
    appreciation_secondary_color: '#FFBA08',
    appreciation_header_bg: '#07070E',
    appreciation_host_name: 'SOBHA DREAM GARDENS',
    appreciation_host_organizer: 'SDG RWA & SDG SPORTS COMMITTEE',
    founder_name: 'Girish Hiremath',
    founder_title: 'Founder, Intelliforge AI',
    founder_signature_data_uri: '',
  })

  useEffect(() => {
    fetch(getApiUrl('/api/info'))
      .then((res) => res.json())
      .then((data) => {
        if (data.branding) setBranding((prev) => ({ ...prev, ...data.branding }))
      })
      .catch(() => {})
  }, [getApiUrl])

  return branding
}

const INVOICE_BRAND_DEFAULTS = {
  primary: '#1e293b',
  accent: '#0284c7',
  secondary: '#6366f1',
  amount: '#4338ca',
  frame: '#e2e8f0',
  text: '#1a202c',
  muted: '#64748b',
  header_text: '#ffffff',
  header_label: '#cbd5e1',
  table_header_bg: '#f8fafc',
  table_border: '#e2e8f0',
  due_bg: '#f0f9ff',
}

function useInvoiceBrand(getApiUrl) {
  const [invoiceBrand, setInvoiceBrand] = useState(INVOICE_BRAND_DEFAULTS)

  useEffect(() => {
    fetch(getApiUrl('/api/info'))
      .then((res) => res.json())
      .then((data) => {
        if (data.invoice_brand) {
          setInvoiceBrand((prev) => ({ ...prev, ...data.invoice_brand }))
        }
      })
      .catch(() => {})
  }, [getApiUrl])

  return invoiceBrand
}

function invoiceBrandStyle(brand) {
  return {
    '--inv-primary': brand.primary,
    '--inv-accent': brand.accent,
    '--inv-secondary': brand.secondary,
    '--inv-amount': brand.amount,
    '--inv-frame': brand.frame,
    '--inv-text': brand.text,
    '--inv-muted': brand.muted,
    '--inv-header-text': brand.header_text,
    '--inv-header-label': brand.header_label,
    '--inv-table-header-bg': brand.table_header_bg,
    '--inv-table-border': brand.table_border,
    '--inv-due-bg': brand.due_bg,
  }
}

function setDocumentMeta(attr, key, value) {
  if (!value) return
  let el = document.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', value)
}

function usePageSeo(branding, sitePath = '/') {
  useEffect(() => {
    const title = `${branding.brand_name} — Certificate Generator`
    const description = (
      `Issue and verify tamper-proof PDF certificates from ${branding.brand_name}. `
      + 'Course participation, sports appreciation, and VTU internship credentials with HMAC-signed shareable verification links.'
    )
    const canonical = `${window.location.origin}${sitePath}`

    document.title = title
    setDocumentMeta('name', 'description', description)
    setDocumentMeta('property', 'og:title', title)
    setDocumentMeta('property', 'og:description', description)
    setDocumentMeta('property', 'og:site_name', branding.brand_name)
    setDocumentMeta('property', 'og:url', canonical)
    setDocumentMeta('name', 'twitter:title', title)
    setDocumentMeta('name', 'twitter:description', description)

    let canonicalEl = document.querySelector('link[rel="canonical"]')
    if (!canonicalEl) {
      canonicalEl = document.createElement('link')
      canonicalEl.setAttribute('rel', 'canonical')
      document.head.appendChild(canonicalEl)
    }
    canonicalEl.setAttribute('href', canonical)

    const jsonLdId = 'site-json-ld'
    let script = document.getElementById(jsonLdId)
    if (!script) {
      script = document.createElement('script')
      script.id = jsonLdId
      script.type = 'application/ld+json'
      document.head.appendChild(script)
    }
    script.textContent = JSON.stringify({
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Organization',
          '@id': `${canonical}#organization`,
          name: branding.brand_name,
          url: canonical,
          email: 'support@intelliforge.tech',
          slogan: branding.org_tagline,
          knowsAbout: ['PDF certificates', 'credential verification', 'VTU internships'],
        },
        {
          '@type': 'WebSite',
          '@id': `${canonical}#website`,
          name: `${branding.brand_name} Certificates`,
          url: canonical,
          description,
          publisher: { '@id': `${canonical}#organization` },
          inLanguage: 'en',
        },
        {
          '@type': 'WebApplication',
          name: `${branding.brand_name} Certificate Generator`,
          url: canonical,
          applicationCategory: 'BusinessApplication',
          operatingSystem: 'Web',
          offers: { '@type': 'Offer', price: '0', priceCurrency: 'INR' },
        },
      ],
    })
  }, [branding, sitePath])
}

function normSignatory(name) {
  return (name || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

function sameSignatory(a, b) {
  const key = normSignatory(a)
  return Boolean(key) && key === normSignatory(b)
}

function uniqueSignatoryRoles(entries) {
  const order = []
  const rolesByKey = {}
  const display = {}
  for (const [name, role] of entries) {
    const n = (name || '').trim()
    if (!n) continue
    const key = normSignatory(n)
    if (!rolesByKey[key]) {
      order.push(key)
      display[key] = n
      rolesByKey[key] = []
    }
    const r = (role || '').trim()
    if (r && !rolesByKey[key].includes(r)) rolesByKey[key].push(r)
  }
  return order.map((k) => [display[k], rolesByKey[k].join(' / ')])
}

const VerifiedBadge = () => (
  <div className="cert-verified">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="14" height="14"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    Verified &amp; Authentic
  </div>
)

function PreviewSignatureBlocks({ signatories }) {
  const blocks = uniqueSignatoryRoles(signatories)
  if (blocks.length === 0) return null
  return (
    <div className="cert-signatures">
      {blocks.map(([name, role]) => (
        <div className="cert-sig-block" key={`${name}-${role}`}>
          <span className="cert-sig-hand">{name}</span>
          <span className="cert-sig-line" />
          <span className="cert-sig-role">{role}</span>
        </div>
      ))}
    </div>
  )
}

function resolveAppreciationHostName(venueName, sponsorLabel, defaultHost) {
  const sponsor = sponsorLabel?.trim() || ''
  let venue = venueName?.trim() || ''
  const placeholders = new Set(['', 'venue / store', 'venue/store', 'venue', 'store', 'sports event'])
  if (placeholders.has(venue.toLowerCase())) venue = ''
  if (sponsor) {
    const low = sponsor.toLowerCase()
    if (!low.includes('intelliforge') && !low.includes('maidaan')) return sponsor
  }
  if (venue) return venue
  return defaultHost || 'SOBHA DREAM GARDENS'
}

function CertificatePreviewCard({
  kind,
  certForm,
  branding,
  certResult,
  getApiUrl,
  previewInstructorName,
}) {
  const previewUrl = certResult?.url || PREVIEW_CERT_URL
  const certId = certResult?.certificate_id || 'CERT-XXXXXXXXXXXX'
  const participantName = certForm.participant_name || 'Participant Name'
  const courseName = certForm.course_name || (
    kind === 'internship'
      ? 'Internship programme'
      : kind === 'appreciation'
        ? certForm.event_name || 'Sports Event'
        : 'Select a course'
  )
  const completionDate = certForm.completion_date || '\u2014'
  const qrSubtitle = certResult?.url
    ? 'QR code links to the permanent verification page.'
    : 'Sample QR — your certificate link appears after generation.'

  if (kind === 'appreciation') {
    const recognition =
      certForm.recognition_text?.trim()
      || (certForm.venue_name?.trim()
        ? `For your commendable participation in sports events organized by ${branding.appreciation_org} at ${certForm.venue_name.trim()}.`
        : 'Recognition text for participation in sports events.')
    const eventName = certForm.event_name?.trim()
    const sponsor = certForm.sponsor_label?.trim()
    const hostName = resolveAppreciationHostName(
      certForm.venue_name,
      sponsor,
      branding.appreciation_host_name,
    )
    const organizer = branding.appreciation_host_organizer || 'SDG RWA & SDG SPORTS COMMITTEE'
    const accent = branding.appreciation_accent || '#F05B00'
    const sidebar = branding.appreciation_sidebar_color || '#0A2818'
    const headerBg = branding.appreciation_header_bg || '#07070E'
    const secondary = branding.appreciation_secondary_color || '#FFBA08'
    const aiColor = branding.appreciation_ai_color || '#7B6FFF'
    const partner = branding.appreciation_partner_org || 'maidaan.academy'
    const dotIdx = partner.indexOf('.')
    const partnerName = dotIdx >= 0 ? partner.slice(0, dotIdx) : partner
    const partnerTld = dotIdx >= 0 ? partner.slice(dotIdx) : ''

    return (
      <div
        className="cert-card cert-card-appreciation"
        style={{
          '--appreciation-accent': accent,
          '--appreciation-sidebar': sidebar,
          '--appreciation-header-bg': headerBg,
          '--appreciation-secondary': secondary,
          '--appreciation-ai': aiColor,
        }}
      >
        <div className="cert-appreciation-header">
          <div className="cert-appreciation-header-col">
            <span className="cert-appreciation-header-label">Sponsored by</span>
            <span className="cert-appreciation-header-rule" />
            <div className="cert-appreciation-brand-row">
              <span className="cert-if-mark" aria-hidden="true">
                <span className="i">I</span>
                <span className="f">F</span>
              </span>
              <span className="cert-if-word">
                {branding.appreciation_org_bold}{' '}
                <em>{branding.appreciation_org_light}</em>
              </span>
            </div>
          </div>
          <div className="cert-appreciation-header-col cert-appreciation-header-col-right">
            <span className="cert-appreciation-header-label">Event technology by</span>
            <span className="cert-appreciation-header-rule" />
            <div className="cert-appreciation-brand-row">
              <span className="cert-maidaan-mark" aria-hidden="true">M</span>
              <span className="cert-maidaan-word">
                {partnerName}
                <span className="tld">{partnerTld}</span>
              </span>
            </div>
          </div>
        </div>
        <div className="cert-appreciation-header-stripe" aria-hidden="true">
          <span className="saffron" /><span className="white" /><span className="green" />
        </div>
        <div className="cert-appreciation-host-strip">
          <div className="cert-appreciation-host-tricolor" aria-hidden="true">
            <span className="saffron" /><span className="white" /><span className="green" />
          </div>
          <p className="cert-appreciation-host-eyebrow">Venue &amp; Host Community</p>
          <p className="cert-appreciation-host-title">{hostName}</p>
          <div className="cert-appreciation-host-ticks" aria-hidden="true">
            <span className="gold" /><span className="saffron" /><span className="green" />
          </div>
          {organizer ? (
            <p className="cert-appreciation-host-organizer">Organized by: {organizer}</p>
          ) : null}
        </div>
        <div className="cert-appreciation-layout">
          <div className="cert-appreciation-main">
            <div className="cert-appreciation-accent-rail" aria-hidden="true">
              <span className="seg1" /><span className="seg2" /><span className="seg3" />
              <span className="seg4" /><span className="seg5" /><span className="seg6" /><span className="seg7" />
            </div>
            <VerifiedBadge />
            <div className="cert-appreciation-body-row">
              <div className="cert-appreciation-sport-seal" aria-hidden="true">
                <span className="seal-icon">&#9733;</span>
                <span className="seal-lbl">Sports</span>
              </div>
              <div className="cert-appreciation-body-content">
                <p className="cert-appreciation-label">{branding.appreciation_presented_label}</p>
                <p className="cert-appreciation-name">
                  <span className="star" aria-hidden="true">&#9733;</span>
                  {participantName}
                  <span className="star" aria-hidden="true">&#9733;</span>
                </p>
                <p className="cert-appreciation-recognition">{recognition}</p>
              </div>
            </div>
            <div className="cert-appreciation-footer">
              <div className="cert-appreciation-date-card">
                <span className="cert-appreciation-date-lbl">&#9654; Date</span>
                <span className="cert-appreciation-date-val">{completionDate}</span>
              </div>
              {eventName ? (
                <div className="cert-appreciation-event">
                  <span className="cert-appreciation-event-lbl">&#9654; Event</span>
                  <strong>{eventName}</strong>
                </div>
              ) : null}
            </div>
            <PreviewQrBlock
              getApiUrl={getApiUrl}
              url={previewUrl}
              title="Scan to verify"
              subtitle={`${qrSubtitle} ID: ${certId}`}
            />
          </div>
          <div className="cert-appreciation-sidebar" aria-hidden="true">
            <div className="cert-appreciation-sidebar-stripes" aria-hidden="true">
              <span className="saffron" /><span className="gold" /><span className="green" /><span className="dark" />
            </div>
            <div className="cert-appreciation-sidebar-body">
              <span>{branding.appreciation_title_line1}</span>
              <span>{branding.appreciation_title_line2}</span>
            </div>
          </div>
        </div>
        <div className="cert-appreciation-tricolor-footer" aria-hidden="true">
          <span className="saffron" /><span className="white" /><span className="green" />
        </div>
      </div>
    )
  }

  if (kind === 'internship') {
    const mentorName = certForm.mentor_name || 'Industry mentor'
    const duration = certForm.internship_duration || '\u2014'
    const hours = certForm.internship_hours || '\u2014'
    const usn = certForm.usn || 'XXXXXXXX'
    const institution = certForm.institution_name?.trim()

    return (
      <div className="cert-card cert-card-internship">
        <div className="cert-forge-bar" aria-hidden="true" />
        <div className="cert-header cert-header-internship">
          <span className="cert-header-badge-float">Internship</span>
          <span className="cert-header-org cert-header-org-internship">{branding.internship_org}</span>
          <span className="cert-header-brand-internship">
            {branding.internship_brand_prefix}{' '}
            <span className="cert-brand-accent">{branding.internship_brand_accent}</span>
          </span>
          <span className="cert-header-sub">
            VTU internship framework &middot; Verifiable credentials &middot; {branding.website}
          </span>
        </div>
        <div className="cert-body">
          <VerifiedBadge />
          <p className="cert-award-label">Certificate of internship completion</p>
          <p className="cert-name">{participantName}</p>
          <p className="cert-usn">USN <strong>{usn}</strong></p>
          {institution ? <p className="cert-institution">{institution}</p> : null}
          <div className="cert-gold-divider" />
          <p className="cert-course">{courseName}</p>
          <div className="cert-meta-row cert-meta-row-internship">
            <div className="cert-meta-item">
              <span className="cert-meta-value">{completionDate}</span>
              <span className="cert-meta-label">Completion</span>
            </div>
            <div className="cert-meta-item">
              <span className="cert-meta-value">{duration}</span>
              <span className="cert-meta-label">Duration</span>
            </div>
            <div className="cert-meta-item">
              <span className="cert-meta-value">{hours}</span>
              <span className="cert-meta-label">Hours</span>
            </div>
            <div className="cert-meta-item">
              <span className="cert-meta-value cert-meta-id">{certId}</span>
              <span className="cert-meta-label">Certificate ID</span>
            </div>
          </div>
          <PreviewSignatureBlocks
            signatories={[
              [branding.founder_name, 'Authorised signatory'],
              [mentorName, 'Industry mentor'],
              [previewInstructorName, 'Program lead'],
            ]}
          />
          <PreviewQrBlock
            getApiUrl={getApiUrl}
            url={previewUrl}
            title="Scan to verify"
            subtitle={qrSubtitle}
          />
        </div>
        <div className="cert-footer-bar">
          Issued by {branding.issued_by} &middot; {branding.website}
        </div>
      </div>
    )
  }

  const showInstructorMeta = !sameSignatory(previewInstructorName, branding.founder_name)

  return (
    <div className="cert-card">
      <div className="cert-header">
        <span className="cert-header-org">{branding.org_tagline}</span>
        <span className="cert-header-brand">{branding.brand_name}</span>
        <span className="cert-header-badge">{branding.participation_title}</span>
      </div>
      <div className="cert-body">
        <VerifiedBadge />
        <p className="cert-award-label">This certificate is awarded to</p>
        <p className="cert-name">{participantName}</p>
        <div className="cert-gold-divider" />
        <p className="cert-course">{courseName}</p>
        <div className="cert-meta-row">
          <div className="cert-meta-item">
            <span className="cert-meta-value">{completionDate}</span>
            <span className="cert-meta-label">Date</span>
          </div>
          {showInstructorMeta && (
            <div className="cert-meta-item cert-meta-bordered">
              <span className="cert-meta-value">{previewInstructorName}</span>
              <span className="cert-meta-label">Instructor</span>
            </div>
          )}
          <div className="cert-meta-item">
            <span className="cert-meta-value cert-meta-id">{certId}</span>
            <span className="cert-meta-label">Certificate ID</span>
          </div>
        </div>
        <PreviewSignatureBlocks
          signatories={[
            [branding.founder_name, branding.founder_title],
            [previewInstructorName, 'Course Instructor'],
          ]}
        />
        <PreviewQrBlock
          getApiUrl={getApiUrl}
          url={previewUrl}
          title="Scan to Verify"
          subtitle={qrSubtitle}
        />
      </div>
      <div className="cert-footer-bar">
        Issued by {branding.issued_by} &middot; {branding.website}
      </div>
    </div>
  )
}

function PreviewQrBlock({ getApiUrl, url, title, subtitle }) {
  const [qrDataUri, setQrDataUri] = useState('')

  useEffect(() => {
    const params = new URLSearchParams({ url })
    fetch(getApiUrl(`/api/preview/qr?${params}`))
      .then((res) => res.json())
      .then((data) => setQrDataUri(data.qr_data_uri || ''))
      .catch(() => setQrDataUri(''))
  }, [url, getApiUrl])

  return (
    <div className="cert-qr-placeholder">
      {qrDataUri ? (
        <img src={qrDataUri} alt={title} className="cert-qr-image" />
      ) : (
        <div className="cert-qr-box" aria-hidden="true">QR</div>
      )}
      <div className="cert-qr-text">
        <strong>{title}</strong>
        {subtitle}
      </div>
    </div>
  )
}

function DeliveryStatus({ success, successText, failureText, detail }) {
  if (success) {
    return <div className="cert-delivery-success">{successText}</div>
  }
  return (
    <div className="cert-delivery-failed" role="alert">
      <strong>{failureText}</strong>
      {detail ? <span>{detail}</span> : null}
    </div>
  )
}

function formatUsdPreview(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return '$0'
  if (Math.abs(n - Math.round(n)) < 0.001) return `$${Math.round(n).toLocaleString('en-US')}`
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatInrPreview(amount) {
  const n = Math.round(Number(amount) || 0)
  return `₹${n.toLocaleString('en-IN')}`
}

function formatInvoiceDatePreview(isoDate) {
  if (!isoDate) return '—'
  const dt = new Date(`${isoDate}T12:00:00`)
  if (Number.isNaN(dt.getTime())) return isoDate
  return dt.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

function calcInvoiceTotals(lineItems, exchangeRate) {
  const totalUsd = (lineItems || []).reduce(
    (sum, item) => sum + (Number(item.rate) || 0) * (Number(item.quantity) || 0),
    0,
  )
  const rate = Number(exchangeRate) || 90
  return {
    totalUsd: Math.round(totalUsd * 100) / 100,
    totalInr: Math.round(totalUsd * rate),
  }
}

function InvoicePreviewCard({ invoiceForm, invoiceResult, invoiceBrand }) {
  const totals = calcInvoiceTotals(invoiceForm.line_items, invoiceForm.exchange_rate)
  const amountWords = invoiceResult?.amount_in_words || '—'
  const addressLines = (text) => (text || '').split(/\r?\n/).filter(Boolean)

  return (
    <div className="invoice-card" style={invoiceBrandStyle(invoiceBrand)}>
      <div className="invoice-card-brand-header">
        <div className="invoice-card-brand-left">
          <span className="invoice-brand-badge">TAX INVOICE</span>
        </div>
        <div className="invoice-card-brand-meta">
          <div className="invoice-meta-row">
            <span>Invoice #</span>
            <strong>{invoiceForm.invoice_number || 'INV-2026-1'}</strong>
          </div>
          <div className="invoice-meta-row">
            <span>Invoice date</span>
            <strong>{formatInvoiceDatePreview(invoiceForm.invoice_date)}</strong>
          </div>
        </div>
      </div>
      <div className="invoice-gold-rule" aria-hidden="true" />

      <div className="invoice-parties">
        <div className="invoice-party">
          <p className="invoice-party-label">BILL FROM:</p>
          <p className="invoice-party-name">{invoiceForm.bill_from_name || 'Vendor name'}</p>
          {addressLines(invoiceForm.bill_from_address).map((line) => (
            <p key={`from-${line}`} className="invoice-party-line">{line}</p>
          ))}
          {invoiceForm.bill_from_email ? (
            <p className="invoice-party-line">email : {invoiceForm.bill_from_email}</p>
          ) : null}
          {invoiceForm.bill_from_pan ? (
            <p className="invoice-party-line">Pan: {invoiceForm.bill_from_pan}</p>
          ) : null}
        </div>
        <div className="invoice-party">
          <p className="invoice-party-label">BILL TO:</p>
          <p className="invoice-party-name">{invoiceForm.bill_to_name || 'Client name'}</p>
          {addressLines(invoiceForm.bill_to_address).map((line) => (
            <p key={`to-${line}`} className="invoice-party-line">{line}</p>
          ))}
          {invoiceForm.bill_to_gstin ? (
            <p className="invoice-party-line">GSTIN: {invoiceForm.bill_to_gstin}</p>
          ) : null}
          {invoiceForm.bill_to_email ? (
            <p className="invoice-party-line">Email : {invoiceForm.bill_to_email}</p>
          ) : null}
        </div>
      </div>

      <table className="invoice-table">
        <thead>
          <tr>
            <th>Description</th>
            <th>Rate</th>
            <th>Quantity</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {(invoiceForm.line_items || []).map((item, idx) => {
            const amount = (Number(item.rate) || 0) * (Number(item.quantity) || 0)
            const rateLabel = item.rate_label?.trim() || formatUsdPreview(item.rate)
            const qtyLabel = item.quantity_label?.trim() || String(item.quantity ?? '')
            return (
              <tr key={`line-${idx}`}>
                <td>{item.description || 'Line item description'}</td>
                <td>{rateLabel}</td>
                <td>{qtyLabel}</td>
                <td className="invoice-amount">{formatUsdPreview(amount)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="invoice-totals">
        <div className="invoice-totals-spacer" />
        <div className="invoice-totals-body">
          <div className="invoice-total-row">
            <span>Total in (USD)</span>
            <strong>{formatUsdPreview(totals.totalUsd)}</strong>
          </div>
          <div className="invoice-total-row invoice-total-inr">
            <span>
              Total in (INR)
              <small>Exchange rate:<br />1 USD = {invoiceForm.exchange_rate || 90} INR</small>
            </span>
            <strong>{formatInrPreview(totals.totalInr)}</strong>
          </div>
        </div>
      </div>

      <p className="invoice-words">
        Amount in words : <strong>{amountWords}</strong>
      </p>

      <div className="invoice-due-wrap">
        <div className="invoice-due-box">
          <span className="invoice-due-label">TOTAL DUE</span>
          <strong className="invoice-due-value">INR {formatInrPreview(totals.totalInr)}</strong>
        </div>
      </div>

      <div className="invoice-signature">
        <p>For: {invoiceForm.signature_name || invoiceForm.bill_from_name || '—'}</p>
        <span>{invoiceForm.signature_name || invoiceForm.bill_from_name || 'Signature'}</span>
      </div>
    </div>
  )
}

function AdminDashboard({ getApiUrl }) {
  const [adminKey, setAdminKey] = useState(() => localStorage.getItem('adminKey') || '')
  const [authenticated, setAuthenticated] = useState(false)
  const [keyInput, setKeyInput] = useState('')
  const [authError, setAuthError] = useState('')

  const [stats, setStats] = useState(null)
  const [certs, setCerts] = useState({ certificates: [], total: 0 })
  const [adminCourses, setAdminCourses] = useState([])
  const [loading, setLoading] = useState(false)
  const [newCourseName, setNewCourseName] = useState('')
  const [newCourseDesc, setNewCourseDesc] = useState('')

  const [bulkEntries, setBulkEntries] = useState([])
  const [bulkResults, setBulkResults] = useState(null)
  const [bulkGenerating, setBulkGenerating] = useState(false)
  const [bulkProgress, setBulkProgress] = useState(0)

  const headers = { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json' }

  const tryAuth = async (key) => {
    try {
      const res = await fetch(getApiUrl('/api/admin/stats'), { headers: { 'X-Admin-Key': key } })
      if (res.ok) {
        setAdminKey(key)
        localStorage.setItem('adminKey', key)
        setAuthenticated(true)
        setAuthError('')
        return true
      }
      setAuthError('Invalid admin key')
      return false
    } catch {
      setAuthError('Connection failed')
      return false
    }
  }

  useEffect(() => {
    if (adminKey) tryAuth(adminKey)
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [statsRes, certsRes, coursesRes] = await Promise.all([
        fetch(getApiUrl('/api/admin/stats'), { headers }),
        fetch(getApiUrl('/api/admin/certificates?limit=20'), { headers }),
        fetch(getApiUrl('/api/admin/courses'), { headers }),
      ])
      if (statsRes.ok) setStats(await statsRes.json())
      if (certsRes.ok) setCerts(await certsRes.json())
      if (coursesRes.ok) {
        const data = await coursesRes.json()
        setAdminCourses(data.courses || [])
      }
    } catch (err) {
      console.error('Admin data load failed:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (authenticated) loadData()
  }, [authenticated])

  const handleLogin = async (e) => {
    e.preventDefault()
    await tryAuth(keyInput)
  }

  const handleLogout = () => {
    setAdminKey('')
    setAuthenticated(false)
    localStorage.removeItem('adminKey')
  }

  const addCourse = async (e) => {
    e.preventDefault()
    if (!newCourseName.trim()) return
    const res = await fetch(getApiUrl('/api/admin/courses'), {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: newCourseName.trim(), description: newCourseDesc.trim() }),
    })
    if (res.ok) {
      setNewCourseName('')
      setNewCourseDesc('')
      loadData()
    }
  }

  const toggleCourse = async (id, active) => {
    await fetch(getApiUrl(`/api/admin/courses/${id}`), {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ active }),
    })
    loadData()
  }

  const revokeCert = async (id) => {
    if (!confirm('Revoke this certificate?')) return
    await fetch(getApiUrl(`/api/admin/certificates/${id}/revoke`), {
      method: 'POST',
      headers,
    })
    loadData()
  }

  const handleCsvUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      const text = evt.target.result
      const lines = text.split(/\r?\n/).filter((l) => l.trim())
      if (lines.length < 2) return
      const headerLine = lines[0].toLowerCase()
      const sep = headerLine.includes('\t') ? '\t' : ','
      const hdrs = headerLine.split(sep).map((h) => h.trim().replace(/^"|"$/g, ''))

      const nameIdx = hdrs.findIndex((h) => /participant|name|student/i.test(h))
      const emailIdx = hdrs.findIndex((h) => /email/i.test(h))
      const courseIdx = hdrs.findIndex((h) => /course/i.test(h))
      const dateIdx = hdrs.findIndex((h) => /date|completion/i.test(h))
      const instrIdx = hdrs.findIndex((h) => /instructor|teacher/i.test(h))

      if (nameIdx === -1) {
        alert('CSV must have a column with "name" or "participant" in the header')
        return
      }

      const entries = []
      for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(sep).map((c) => c.trim().replace(/^"|"$/g, ''))
        const pName = cols[nameIdx]?.trim()
        if (!pName) continue
        entries.push({
          participant_name: pName,
          participant_email: emailIdx >= 0 ? cols[emailIdx]?.trim() || '' : '',
          course_name: courseIdx >= 0 ? cols[courseIdx]?.trim() || '' : '',
          completion_date: dateIdx >= 0 ? cols[dateIdx]?.trim() || '' : '',
          instructor_name: instrIdx >= 0 ? cols[instrIdx]?.trim() || 'Certificate Team' : 'Certificate Team',
        })
      }
      setBulkEntries(entries)
      setBulkResults(null)
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const removeBulkEntry = (idx) => {
    setBulkEntries((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateBulkEntry = (idx, field, value) => {
    setBulkEntries((prev) => prev.map((e, i) => (i === idx ? { ...e, [field]: value } : e)))
  }

  const generateBulk = async () => {
    if (bulkEntries.length === 0) return
    setBulkGenerating(true)
    setBulkProgress(0)
    setBulkResults(null)
    try {
      const BATCH = 50
      const allResults = []
      for (let start = 0; start < bulkEntries.length; start += BATCH) {
        const batch = bulkEntries.slice(start, start + BATCH)
        const res = await fetch(getApiUrl('/api/admin/certificates/bulk'), {
          method: 'POST',
          headers,
          body: JSON.stringify({ entries: batch }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Request failed' }))
          batch.forEach((_, i) =>
            allResults.push({ index: start + i, status: 'error', error: err.detail || 'Request failed' })
          )
        } else {
          const data = await res.json()
          allResults.push(...data.results.map((r) => ({ ...r, index: start + r.index })))
        }
        setBulkProgress(Math.min(start + BATCH, bulkEntries.length))
      }
      const succeeded = allResults.filter((r) => r.status === 'success').length
      const failed = allResults.filter((r) => r.status === 'error').length
      setBulkResults({ total: bulkEntries.length, succeeded, failed, results: allResults })
      loadData()
    } catch (err) {
      setBulkResults({ total: bulkEntries.length, succeeded: 0, failed: bulkEntries.length, results: [], error: err.message })
    } finally {
      setBulkGenerating(false)
    }
  }

  const downloadBulkCsv = () => {
    if (!bulkResults?.results?.length) return
    const successful = bulkResults.results.filter((r) => r.status === 'success')
    if (successful.length === 0) return
    const lines = ['Certificate ID,Participant,Course,Email Sent,URL,Download URL']
    successful.forEach((r) => {
      lines.push(`"${r.certificate_id}","${r.participant_name}","${r.course_name}","${r.email_sent ? 'Yes' : 'No'}","${r.url}","${r.download_url}"`)
    })
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `certificates_bulk_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  if (!authenticated) {
    return (
      <div className="admin-login">
        <div className="admin-login-card">
          <h3>Admin Dashboard</h3>
          <p>Enter admin key to access the dashboard</p>
          <form onSubmit={handleLogin}>
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="Admin key"
              autoFocus
            />
            <button type="submit" className="download-btn">Authenticate</button>
          </form>
          {authError && <p className="admin-error">{authError}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="admin-dashboard">
      <div className="admin-topbar">
        <h2>Admin Dashboard</h2>
        <button onClick={handleLogout} className="admin-logout-btn">Logout</button>
      </div>

      {loading && <div className="admin-loading">Loading...</div>}

      {stats && (
        <div className="admin-stats">
          <div className="stat-card">
            <span className="stat-value">{stats.total_certificates}</span>
            <span className="stat-label">Total Certificates</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{stats.this_week}</span>
            <span className="stat-label">This Week</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{stats.revoked}</span>
            <span className="stat-label">Revoked</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{adminCourses.filter(c => c.active).length}</span>
            <span className="stat-label">Active Courses</span>
          </div>
        </div>
      )}

      {stats?.by_course?.length > 0 && (
        <div className="admin-section">
          <h3>Certificates by Course</h3>
          <div className="admin-bar-chart">
            {stats.by_course.map((item) => (
              <div key={item.course_name} className="bar-row">
                <span className="bar-label">{item.course_name}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ width: `${Math.max(4, (item.cnt / stats.total_certificates) * 100)}%` }}
                  />
                </div>
                <span className="bar-value">{item.cnt}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="admin-section">
        <h3>Recent Certificates</h3>
        {certs.certificates.length === 0 ? (
          <p className="admin-empty">No certificates issued yet</p>
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Participant</th>
                  <th>Course</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {certs.certificates.map((c) => (
                  <tr key={c.id} className={c.revoked ? 'row-revoked' : ''}>
                    <td className="td-mono">{c.certificate_id}</td>
                    <td>{c.participant_name}</td>
                    <td>{c.course_name}</td>
                    <td className="td-mono">{c.completion_date}</td>
                    <td>
                      <span className={`status-badge ${c.revoked ? 'status-revoked' : 'status-active'}`}>
                        {c.revoked ? 'Revoked' : 'Active'}
                      </span>
                    </td>
                    <td>
                      {!c.revoked && (
                        <button onClick={() => revokeCert(c.id)} className="admin-action-btn danger">
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {certs.total > 20 && (
          <p className="admin-meta">Showing 20 of {certs.total} certificates</p>
        )}
      </div>

      <div className="admin-section">
        <h3>Bulk Generate Certificates</h3>
        <div className="bulk-upload-area">
          <label className="bulk-upload-label">
            <input type="file" accept=".csv,.tsv,.txt" onChange={handleCsvUpload} hidden />
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <span>Upload CSV File</span>
            <span className="bulk-upload-hint">Columns: participant_name (required), email, course_name, completion_date, instructor_name</span>
          </label>
        </div>

        {bulkEntries.length > 0 && !bulkResults && (
          <div className="bulk-preview">
            <div className="bulk-preview-header">
              <span>{bulkEntries.length} entries ready</span>
              <div className="bulk-preview-actions">
                <button onClick={() => setBulkEntries([])} className="admin-action-btn">Clear</button>
                <button onClick={generateBulk} disabled={bulkGenerating} className="download-btn">
                  {bulkGenerating ? `Generating... (${bulkProgress}/${bulkEntries.length})` : `Generate ${bulkEntries.length} Certificates`}
                </button>
              </div>
            </div>
            {bulkGenerating && (
              <div className="bulk-progress-track">
                <div className="bulk-progress-fill" style={{ width: `${(bulkProgress / bulkEntries.length) * 100}%` }} />
              </div>
            )}
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Participant</th>
                    <th>Email</th>
                    <th>Course</th>
                    <th>Date</th>
                    <th>Instructor</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {bulkEntries.slice(0, 50).map((entry, idx) => (
                    <tr key={idx}>
                      <td className="td-mono">{idx + 1}</td>
                      <td>
                        <input className="bulk-inline-input" value={entry.participant_name}
                          onChange={(e) => updateBulkEntry(idx, 'participant_name', e.target.value)} />
                      </td>
                      <td>
                        <input type="email" className="bulk-inline-input" value={entry.participant_email || ''}
                          placeholder="email"
                          onChange={(e) => updateBulkEntry(idx, 'participant_email', e.target.value)} />
                      </td>
                      <td>
                        <select className="bulk-inline-select" value={entry.course_name}
                          onChange={(e) => updateBulkEntry(idx, 'course_name', e.target.value)}>
                          <option value="">Select course</option>
                          {adminCourses.filter((c) => c.active).map((c) => (
                            <option key={c.id} value={c.name}>{c.name}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input type="date" className="bulk-inline-input" value={entry.completion_date}
                          onChange={(e) => updateBulkEntry(idx, 'completion_date', e.target.value)} />
                      </td>
                      <td>
                        <input className="bulk-inline-input" value={entry.instructor_name}
                          onChange={(e) => updateBulkEntry(idx, 'instructor_name', e.target.value)} />
                      </td>
                      <td>
                        <button onClick={() => removeBulkEntry(idx)} className="admin-action-btn danger" title="Remove">✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {bulkEntries.length > 50 && (
              <p className="admin-meta">Showing first 50 of {bulkEntries.length} entries</p>
            )}
          </div>
        )}

        {bulkResults && (
          <div className="bulk-results">
            <div className="bulk-results-summary">
              <div className={`bulk-stat ${bulkResults.succeeded > 0 ? 'bulk-stat-success' : ''}`}>
                <span className="stat-value">{bulkResults.succeeded}</span>
                <span className="stat-label">Succeeded</span>
              </div>
              <div className={`bulk-stat ${bulkResults.failed > 0 ? 'bulk-stat-error' : ''}`}>
                <span className="stat-value">{bulkResults.failed}</span>
                <span className="stat-label">Failed</span>
              </div>
              <div className="bulk-stat">
                <span className="stat-value">{bulkResults.total}</span>
                <span className="stat-label">Total</span>
              </div>
            </div>
            <div className="bulk-results-actions">
              {bulkResults.succeeded > 0 && (
                <button onClick={downloadBulkCsv} className="download-btn">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Download Results CSV
                </button>
              )}
              <button onClick={() => { setBulkResults(null); setBulkEntries([]) }} className="admin-action-btn">
                New Batch
              </button>
            </div>
            {bulkResults.results.filter((r) => r.status === 'error').length > 0 && (
              <div className="bulk-errors">
                <h4>Errors</h4>
                {bulkResults.results.filter((r) => r.status === 'error').map((r) => (
                  <div key={r.index} className="bulk-error-row">
                    <span className="td-mono">Row {r.index + 1}:</span> {r.error}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="admin-section">
        <h3>Course Management</h3>
        <form className="admin-add-course" onSubmit={addCourse}>
          <input
            type="text"
            value={newCourseName}
            onChange={(e) => setNewCourseName(e.target.value)}
            placeholder="New course name"
            required
          />
          <input
            type="text"
            value={newCourseDesc}
            onChange={(e) => setNewCourseDesc(e.target.value)}
            placeholder="Description (optional)"
          />
          <button type="submit" className="download-btn">Add Course</button>
        </form>
        <div className="admin-courses-list">
          {adminCourses.map((c) => (
            <div key={c.id} className={`admin-course-item ${!c.active ? 'course-inactive' : ''}`}>
              <div className="course-info">
                <span className="course-name">{c.name}</span>
                {c.description && <span className="course-desc">{c.description}</span>}
              </div>
              <button
                onClick={() => toggleCourse(c.id, !c.active)}
                className={`admin-action-btn ${c.active ? 'danger' : 'success'}`}
              >
                {c.active ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState('certificate')
  const [courses, setCourses] = useState([])
  const [coursesLoading, setCoursesLoading] = useState(true)

  const getApiUrl = (path) => path

  const branding = useBranding(getApiUrl)
  const invoiceBrand = useInvoiceBrand(getApiUrl)
  usePageSeo(branding)

  useEffect(() => {
    fetch(getApiUrl('/api/courses'))
      .then((res) => res.json())
      .then((data) => setCourses(data.courses || []))
      .catch(() => setCourses([]))
      .finally(() => setCoursesLoading(false))
  }, [])

  const [certForm, setCertForm] = useState({
    certificate_kind: 'participation',
    participant_name: '',
    participant_email: '',
    course_name: '',
    completion_date: new Date().toISOString().split('T')[0],
    instructor_name: 'Certificate Team',
    usn: '',
    internship_duration: '',
    internship_hours: '',
    mentor_name: '',
    institution_name: '',
    recognition_text: '',
    event_name: '',
    venue_name: 'Sobha Dream Gardens',
    sponsor_label: '',
  })
  const [isGenerating, setIsGenerating] = useState(false)
  const [certError, setCertError] = useState(null)
  const [certResult, setCertResult] = useState(null)

  const [invoiceForm, setInvoiceForm] = useState({
    invoice_number: 'INV-2026-1',
    invoice_date: new Date().toISOString().split('T')[0],
    bill_from_name: 'Naveen Katiyar',
    bill_from_address: '68, Vijaynagar, Kanpur\nUttar Pradesh',
    bill_from_email: '',
    bill_from_pan: 'XXXXXXX30A',
    bill_to_name: 'Cognyzer',
    bill_to_address:
      'Building No.3, Sukan Mall\nBeside Rajasthan Hospital, Shahibaug,\nAhmedabad,\nGujarat - 380004',
    bill_to_gstin: '24AAWFC3808N1ZX',
    bill_to_email: 'team@cognyzer.com',
    exchange_rate: 90,
    signature_name: 'Naveen Katiyar',
    line_items: [
      {
        description:
          'Dataset preparation and validation services as per agreed specifications for Project : Terminus (Terminal Bench 2.0)',
        rate: 22,
        rate_label: '$22 / Task',
        quantity: 10,
        quantity_label: '10 task',
      },
    ],
  })
  const [isGeneratingInvoice, setIsGeneratingInvoice] = useState(false)
  const [invoiceError, setInvoiceError] = useState(null)
  const [invoiceResult, setInvoiceResult] = useState(null)

  const previewInstructorName = certForm.instructor_name || 'Certificate Team'

  const generateCertificate = async (e) => {
    e.preventDefault()
    setIsGenerating(true)
    setCertError(null)
    setCertResult(null)

    try {
      if (!certForm.participant_name.trim()) throw new Error('Please enter participant name')
      if (!certForm.completion_date) throw new Error('Please select a date')
      if (certForm.certificate_kind === 'participation' && !certForm.course_name) {
        throw new Error('Please select a course')
      }
      if (certForm.certificate_kind === 'appreciation') {
        if (!certForm.recognition_text?.trim() && !certForm.venue_name?.trim()) {
          throw new Error('Recognition text or venue is required for appreciation certificates')
        }
      }
      if (certForm.certificate_kind === 'internship') {
        if (!certForm.usn?.trim()) throw new Error('USN is required for internship certificates')
        if (!certForm.internship_duration?.trim()) throw new Error('Internship duration is required')
        if (!certForm.internship_hours?.trim()) throw new Error('Internship hours are required')
        if (!certForm.mentor_name?.trim()) throw new Error('Industry mentor name is required')
      }

      const payload = {
        participant_name: certForm.participant_name.trim(),
        completion_date: certForm.completion_date,
        instructor_name: (certForm.instructor_name || 'Certificate Team').trim(),
      }
      if (certForm.certificate_kind !== 'appreciation') {
        payload.course_name = certForm.course_name
      }
      if (certForm.participant_email?.trim()) {
        payload.participant_email = certForm.participant_email.trim()
      }
      if (certForm.certificate_kind === 'appreciation') {
        payload.certificate_kind = 'appreciation'
        if (certForm.recognition_text?.trim()) {
          payload.recognition_text = certForm.recognition_text.trim()
        }
        if (certForm.venue_name?.trim()) payload.venue_name = certForm.venue_name.trim()
        if (certForm.event_name?.trim()) payload.event_name = certForm.event_name.trim()
        if (certForm.sponsor_label?.trim()) payload.sponsor_label = certForm.sponsor_label.trim()
      } else if (certForm.certificate_kind === 'internship') {
        payload.certificate_kind = 'internship'
        payload.usn = certForm.usn.trim()
        payload.internship_duration = certForm.internship_duration.trim()
        payload.internship_hours = certForm.internship_hours.trim()
        payload.mentor_name = certForm.mentor_name.trim()
        if (certForm.institution_name?.trim()) {
          payload.institution_name = certForm.institution_name.trim()
        }
      }

      const response = await fetch(getApiUrl('/api/certificate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(45000),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        const detail = errorData.detail
        const msg =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join(' ')
              : `Server error: ${response.status}`
        throw new Error(msg)
      }

      const data = await response.json()
      setCertResult(data)
    } catch (err) {
      console.error('Error generating certificate:', err)
      if (err.name === 'TimeoutError' || err.name === 'AbortError') {
        setCertError('Request timed out. Check your connection and try again.')
      } else if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError')) {
        setCertError('Could not reach the certificate API. If developing locally, start the backend on port 8000.')
      } else {
        setCertError(err.message)
      }
    } finally {
      setIsGenerating(false)
    }
  }

  const downloadPdfDirect = async () => {
    if (!certResult?.download_url) return
    try {
      const response = await fetch(certResult.download_url)
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const prefix =
        certResult.certificate_kind === 'internship'
          ? 'Internship_Certificate_'
          : certResult.certificate_kind === 'appreciation'
            ? 'Appreciation_Certificate_'
            : 'Certificate_'
      a.download = `${prefix}${certResult.participant_name.replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch {
      window.open(certResult.download_url, '_blank')
    }
  }

  const [copied, setCopied] = useState(false)

  const copyShareableLink = async () => {
    if (!certResult?.url) return
    try {
      await navigator.clipboard.writeText(certResult.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const input = document.createElement('input')
      input.value = certResult.url
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const updateCertField = (field, value) => {
    setCertForm((prev) => ({ ...prev, [field]: value }))
    setCertError(null)
    setCertResult(null)
  }

  const updateInvoiceField = (field, value) => {
    setInvoiceForm((prev) => ({ ...prev, [field]: value }))
    setInvoiceError(null)
    setInvoiceResult(null)
  }

  const updateInvoiceLineItem = (index, field, value) => {
    setInvoiceForm((prev) => ({
      ...prev,
      line_items: prev.line_items.map((item, i) =>
        i === index ? { ...item, [field]: value } : item,
      ),
    }))
    setInvoiceError(null)
    setInvoiceResult(null)
  }

  const addInvoiceLineItem = () => {
    setInvoiceForm((prev) => ({
      ...prev,
      line_items: [
        ...prev.line_items,
        { description: '', rate: 0, rate_label: '', quantity: 1, quantity_label: '' },
      ],
    }))
    setInvoiceResult(null)
  }

  const removeInvoiceLineItem = (index) => {
    setInvoiceForm((prev) => ({
      ...prev,
      line_items: prev.line_items.filter((_, i) => i !== index),
    }))
    setInvoiceResult(null)
  }

  const generateInvoice = async (e) => {
    e.preventDefault()
    setIsGeneratingInvoice(true)
    setInvoiceError(null)
    setInvoiceResult(null)

    try {
      if (!invoiceForm.bill_from_name.trim()) throw new Error('Bill from name is required')
      if (!invoiceForm.bill_to_name.trim()) throw new Error('Bill to name is required')
      if (!invoiceForm.invoice_date) throw new Error('Invoice date is required')
      if (!invoiceForm.line_items.length) throw new Error('Add at least one line item')

      const payload = {
        invoice_number: invoiceForm.invoice_number.trim(),
        invoice_date: invoiceForm.invoice_date,
        bill_from_name: invoiceForm.bill_from_name.trim(),
        bill_from_address: invoiceForm.bill_from_address.trim(),
        bill_from_email: invoiceForm.bill_from_email.trim(),
        bill_from_pan: invoiceForm.bill_from_pan.trim(),
        bill_to_name: invoiceForm.bill_to_name.trim(),
        bill_to_address: invoiceForm.bill_to_address.trim(),
        bill_to_gstin: invoiceForm.bill_to_gstin.trim(),
        bill_to_email: invoiceForm.bill_to_email.trim(),
        exchange_rate: Number(invoiceForm.exchange_rate) || 90,
        signature_name: (invoiceForm.signature_name || invoiceForm.bill_from_name).trim(),
        line_items: invoiceForm.line_items.map((item) => ({
          description: item.description.trim(),
          rate: Number(item.rate) || 0,
          rate_label: item.rate_label?.trim() || '',
          quantity: Number(item.quantity) || 0,
          quantity_label: item.quantity_label?.trim() || '',
        })),
      }

      for (const [idx, item] of payload.line_items.entries()) {
        if (!item.description) throw new Error(`Line item ${idx + 1}: description is required`)
      }

      const response = await fetch(getApiUrl('/api/invoice'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(45000),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        const detail = errorData.detail || errorData.error?.message
        const msg =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join(' ')
              : `Server error: ${response.status}`
        throw new Error(msg)
      }

      const data = await response.json()
      setInvoiceResult(data)
      if (!invoiceForm.invoice_number.trim() && data.invoice_number) {
        setInvoiceForm((prev) => ({ ...prev, invoice_number: data.invoice_number }))
      }
    } catch (err) {
      console.error('Error generating invoice:', err)
      if (err.name === 'TimeoutError' || err.name === 'AbortError') {
        setInvoiceError('Request timed out. Check your connection and try again.')
      } else if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError')) {
        setInvoiceError('Could not reach the API. If developing locally, start the backend on port 8000.')
      } else {
        setInvoiceError(err.message)
      }
    } finally {
      setIsGeneratingInvoice(false)
    }
  }

  const downloadInvoicePdf = async () => {
    if (!invoiceResult?.download_url) return
    try {
      const response = await fetch(invoiceResult.download_url)
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Invoice_${(invoiceResult.invoice_number || 'invoice').replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch {
      window.open(invoiceResult.download_url, '_blank')
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand-link" aria-label={branding.brand_name}>
          <div className="header-icon">
            <CertIcon size={32} />
          </div>
          <span className="brand-wordmark">{branding.brand_name}</span>
        </div>
        <h1>{branding.brand_name}</h1>
        <p className="header-subtitle">
          {activeTab === 'admin'
            ? 'Manage courses, bulk certificates, and platform analytics'
            : activeTab === 'invoice'
              ? 'Create tax invoices with USD line items, INR conversion, and downloadable PDFs'
              : 'Create tamper-proof PDF certificates and VTU internship credentials with shareable verification links'}
        </p>
        <nav className="tab-nav" role="tablist">
          <button
            className={`tab-btn ${activeTab === 'certificate' ? 'active' : ''}`}
            onClick={() => setActiveTab('certificate')}
            role="tab"
            aria-selected={activeTab === 'certificate'}
          >
            <Icon.CertTab />
            <span>Generate Certificate</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'invoice' ? 'active' : ''}`}
            onClick={() => setActiveTab('invoice')}
            role="tab"
            aria-selected={activeTab === 'invoice'}
          >
            <Icon.Invoice />
            <span>Generate Invoice</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => setActiveTab('admin')}
            role="tab"
            aria-selected={activeTab === 'admin'}
          >
            <Icon.Admin />
            <span>Admin</span>
          </button>
        </nav>
      </header>

      {activeTab === 'certificate' && (
        <div className="cert-container">
          <div className="cert-form-section">
            <div className="section-header">
              <h2>Certificate Details</h2>
            </div>
            <form className="cert-form" onSubmit={generateCertificate}>
              <fieldset className="form-group cert-type-fieldset">
                <legend className="cert-type-legend">Certificate type</legend>
                <div className="cert-type-toggle" role="radiogroup" aria-label="Certificate type">
                  <button
                    type="button"
                    className={certForm.certificate_kind === 'participation' ? 'active' : ''}
                    onClick={() => updateCertField('certificate_kind', 'participation')}
                    aria-pressed={certForm.certificate_kind === 'participation'}
                  >
                    Course participation
                  </button>
                  <button
                    type="button"
                    className={certForm.certificate_kind === 'internship' ? 'active' : ''}
                    onClick={() => updateCertField('certificate_kind', 'internship')}
                    aria-pressed={certForm.certificate_kind === 'internship'}
                  >
                    VTU internship completion
                  </button>
                  <button
                    type="button"
                    className={certForm.certificate_kind === 'appreciation' ? 'active' : ''}
                    onClick={() => updateCertField('certificate_kind', 'appreciation')}
                    aria-pressed={certForm.certificate_kind === 'appreciation'}
                  >
                    Sports appreciation
                  </button>
                </div>
                <p className="form-hint">
                  {certForm.certificate_kind === 'internship'
                    ? 'Internship mode adds USN, duration, hours, and mentor for the Forge PDF and verify link.'
                    : certForm.certificate_kind === 'appreciation'
                      ? 'Appreciation mode uses a landscape sports-event layout — recognition text, venue, and optional event branding.'
                      : 'Standard course completion certificate with instructor signature and verification QR.'}
                </p>
              </fieldset>

              <div className="form-group">
                <label htmlFor="participant_name">Participant Name</label>
                <input
                  id="participant_name"
                  type="text"
                  placeholder="e.g. Jane Doe"
                  value={certForm.participant_name}
                  onChange={(e) => updateCertField('participant_name', e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="participant_email">Participant Email <span className="form-optional">(optional – certificate will be emailed)</span></label>
                <input
                  id="participant_email"
                  type="email"
                  placeholder="e.g. jane@example.com"
                  value={certForm.participant_email}
                  onChange={(e) => updateCertField('participant_email', e.target.value)}
                />
              </div>

              {certForm.certificate_kind !== 'appreciation' && (
                <div className="form-group">
                  <label htmlFor="course_name">
                    {certForm.certificate_kind === 'internship'
                      ? 'Internship programme / course'
                      : 'Training course'}
                  </label>
                  <select
                    id="course_name"
                    value={certForm.course_name}
                    onChange={(e) => updateCertField('course_name', e.target.value)}
                    required={certForm.certificate_kind === 'participation'}
                    disabled={coursesLoading}
                  >
                    <option value="">{coursesLoading ? 'Loading courses...' : 'Select a course'}</option>
                    {courses.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              )}

              {certForm.certificate_kind === 'appreciation' && (
                <>
                  <div className="form-group">
                    <label htmlFor="recognition_text">
                      Recognition text
                      <span className="form-optional"> (or leave blank to auto-generate from venue)</span>
                    </label>
                    <textarea
                      id="recognition_text"
                      rows={3}
                      placeholder="For your commendable participation in sports events organized by IntelliForge AI at Sobha Dream Gardens."
                      value={certForm.recognition_text}
                      onChange={(e) => updateCertField('recognition_text', e.target.value)}
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="venue_name">Venue / host community</label>
                      <input
                        id="venue_name"
                        type="text"
                        placeholder="e.g. Sobha Dream Gardens"
                        value={certForm.venue_name}
                        onChange={(e) => updateCertField('venue_name', e.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="event_name">Event name</label>
                      <input
                        id="event_name"
                        type="text"
                        placeholder="e.g. Independence Day Sports Festival 2026"
                        value={certForm.event_name}
                        onChange={(e) => updateCertField('event_name', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label htmlFor="sponsor_label">
                      Host label override
                      <span className="form-optional"> (optional — defaults to venue or SOBHA DREAM GARDENS)</span>
                    </label>
                    <input
                      id="sponsor_label"
                      type="text"
                      placeholder="e.g. SOBHA DREAM GARDENS"
                      value={certForm.sponsor_label}
                      onChange={(e) => updateCertField('sponsor_label', e.target.value)}
                    />
                  </div>
                </>
              )}

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="completion_date">Completion Date</label>
                  <input
                    id="completion_date"
                    type="date"
                    value={certForm.completion_date}
                    onChange={(e) => updateCertField('completion_date', e.target.value)}
                    required
                  />
                </div>
                {certForm.certificate_kind !== 'appreciation' && (
                  <div className="form-group">
                    <label htmlFor="instructor_name">
                      {certForm.certificate_kind === 'internship' ? 'Program lead' : 'Instructor name'}
                    </label>
                    <input
                      id="instructor_name"
                      type="text"
                      placeholder={
                        certForm.certificate_kind === 'internship'
                          ? 'e.g. Program Lead'
                          : 'Certificate Team'
                      }
                      value={certForm.instructor_name}
                      onChange={(e) => updateCertField('instructor_name', e.target.value)}
                    />
                  </div>
                )}
              </div>

              {certForm.certificate_kind === 'internship' && (
                <>
                  <div className="form-group">
                    <label htmlFor="usn">USN (University Seat Number)</label>
                    <input
                      id="usn"
                      type="text"
                      placeholder="e.g. 1RV22CS014"
                      value={certForm.usn}
                      onChange={(e) => updateCertField('usn', e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="internship_duration">Internship duration</label>
                      <input
                        id="internship_duration"
                        type="text"
                        placeholder="e.g. January 2026 – June 2026"
                        value={certForm.internship_duration}
                        onChange={(e) => updateCertField('internship_duration', e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="internship_hours">Contact hours</label>
                      <input
                        id="internship_hours"
                        type="text"
                        placeholder="e.g. 120"
                        value={certForm.internship_hours}
                        onChange={(e) => updateCertField('internship_hours', e.target.value)}
                        required
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label htmlFor="mentor_name">Industry mentor</label>
                    <input
                      id="mentor_name"
                      type="text"
                      placeholder="Mentor name (appears on certificate)"
                      value={certForm.mentor_name}
                      onChange={(e) => updateCertField('mentor_name', e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="institution_name">
                      College / institution <span className="form-optional">(optional)</span>
                    </label>
                    <input
                      id="institution_name"
                      type="text"
                      placeholder="Affiliated college name (VTU)"
                      value={certForm.institution_name}
                      onChange={(e) => updateCertField('institution_name', e.target.value)}
                    />
                  </div>
                </>
              )}

              {certError && (
                <div className="error-message" role="alert">
                  <strong>Error:</strong> {certError}
                </div>
              )}

              <button
                type="submit"
                className="download-btn cert-submit-btn"
                disabled={isGenerating}
              >
                {isGenerating ? <Icon.Loader /> : <Icon.Award />}
                <span>
                  {isGenerating
                    ? 'Generating...'
                    : certForm.certificate_kind === 'internship'
                      ? 'Generate internship certificate'
                      : certForm.certificate_kind === 'appreciation'
                        ? 'Generate appreciation certificate'
                        : 'Generate certificate'}
                </span>
              </button>
            </form>

            {certResult && (
              <div className="cert-result">
                <div className="cert-result-header">
                  <span className="cert-result-check"><Icon.CheckCircle /></span>
                  Certificate issued for <strong>{certResult.participant_name}</strong>
                  {certResult.certificate_kind === 'internship' && (
                    <span className="cert-kind-badge">VTU internship</span>
                  )}
                  {certResult.certificate_kind === 'appreciation' && (
                    <span className="cert-kind-badge cert-kind-badge-appreciation">Appreciation</span>
                  )}
                  <span className="cert-id-badge">{certResult.certificate_id}</span>
                </div>
                {certForm.participant_email && (
                  <DeliveryStatus
                    success={certResult.email_sent}
                    successText={
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                        {' '}Certificate emailed to {certForm.participant_email}
                      </>
                    }
                    failureText="Email delivery failed."
                    detail={certResult.email_error || 'Share the certificate link below instead.'}
                  />
                )}

                <div className="cert-link-box">
                  <label className="cert-link-label">Permanent Shareable Link</label>
                  <div className="cert-link-row">
                    <input
                      className="cert-link-input"
                      type="text"
                      value={certResult.url}
                      readOnly
                      onClick={(e) => e.target.select()}
                      aria-label="Certificate shareable link"
                    />
                    <button className="cert-link-copy" onClick={copyShareableLink} type="button">
                      {copied ? <Icon.Check /> : <Icon.Copy />}
                      <span>{copied ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                </div>

                <div className="cert-result-actions">
                  <button
                    className="download-btn cert-action-btn"
                    onClick={downloadPdfDirect}
                    type="button"
                  >
                    <Icon.Download />
                    <span>Download PDF</span>
                  </button>
                  <a
                    className="cert-view-btn cert-action-btn"
                    href={certResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Icon.ExternalLink />
                    <span>View Public Page</span>
                  </a>
                </div>

                <div className="cert-share-row">
                  <a
                    className="cert-share-btn cert-share-linkedin"
                    href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(certResult.url)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M20.5 2h-17A1.5 1.5 0 002 3.5v17A1.5 1.5 0 003.5 22h17a1.5 1.5 0 001.5-1.5v-17A1.5 1.5 0 0020.5 2zM8 19H5v-9h3zM6.5 8.25A1.75 1.75 0 118.3 6.5a1.78 1.78 0 01-1.8 1.75zM19 19h-3v-4.74c0-1.42-.6-1.93-1.38-1.93A1.74 1.74 0 0013 14.19V19h-3v-9h2.9v1.3a3.11 3.11 0 012.7-1.4c1.55 0 3.36.86 3.36 3.66z"/></svg>
                    Share on LinkedIn
                  </a>
                  <a
                    className="cert-share-btn cert-share-twitter"
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`I completed ${certResult.course_name} — ${branding.brand_name}!`)}&url=${encodeURIComponent(certResult.url)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                    Share on X
                  </a>
                </div>
              </div>
            )}
          </div>

          <div className="cert-preview-section">
            <div className="section-header">
              <h2>Certificate Preview</h2>
            </div>
            <div className="cert-preview">
              <CertificatePreviewCard
                kind={certForm.certificate_kind}
                certForm={certForm}
                branding={branding}
                certResult={certResult}
                getApiUrl={getApiUrl}
                previewInstructorName={previewInstructorName}
              />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'invoice' && (
        <div className="cert-container invoice-container">
          <div className="cert-form-section">
            <div className="section-header">
              <h2>Invoice Details</h2>
            </div>
            <form className="cert-form" onSubmit={generateInvoice}>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="invoice_number">Invoice #</label>
                  <input
                    id="invoice_number"
                    type="text"
                    placeholder="Auto-generated if blank"
                    value={invoiceForm.invoice_number}
                    onChange={(e) => updateInvoiceField('invoice_number', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="invoice_date">Invoice date</label>
                  <input
                    id="invoice_date"
                    type="date"
                    value={invoiceForm.invoice_date}
                    onChange={(e) => updateInvoiceField('invoice_date', e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="exchange_rate">USD → INR exchange rate</label>
                  <input
                    id="exchange_rate"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={invoiceForm.exchange_rate}
                    onChange={(e) => updateInvoiceField('exchange_rate', e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="signature_name">Signature name</label>
                  <input
                    id="signature_name"
                    type="text"
                    placeholder="Defaults to bill-from name"
                    value={invoiceForm.signature_name}
                    onChange={(e) => updateInvoiceField('signature_name', e.target.value)}
                  />
                </div>
              </div>

              <fieldset className="form-group invoice-party-fieldset">
                <legend>Bill from</legend>
                <div className="form-group">
                  <label htmlFor="bill_from_name">Name</label>
                  <input
                    id="bill_from_name"
                    type="text"
                    value={invoiceForm.bill_from_name}
                    onChange={(e) => updateInvoiceField('bill_from_name', e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="bill_from_address">Address</label>
                  <textarea
                    id="bill_from_address"
                    rows={3}
                    value={invoiceForm.bill_from_address}
                    onChange={(e) => updateInvoiceField('bill_from_address', e.target.value)}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="bill_from_email">Email</label>
                    <input
                      id="bill_from_email"
                      type="email"
                      value={invoiceForm.bill_from_email}
                      onChange={(e) => updateInvoiceField('bill_from_email', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="bill_from_pan">PAN</label>
                    <input
                      id="bill_from_pan"
                      type="text"
                      value={invoiceForm.bill_from_pan}
                      onChange={(e) => updateInvoiceField('bill_from_pan', e.target.value)}
                    />
                  </div>
                </div>
              </fieldset>

              <fieldset className="form-group invoice-party-fieldset">
                <legend>Bill to</legend>
                <div className="form-group">
                  <label htmlFor="bill_to_name">Name</label>
                  <input
                    id="bill_to_name"
                    type="text"
                    value={invoiceForm.bill_to_name}
                    onChange={(e) => updateInvoiceField('bill_to_name', e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="bill_to_address">Address</label>
                  <textarea
                    id="bill_to_address"
                    rows={4}
                    value={invoiceForm.bill_to_address}
                    onChange={(e) => updateInvoiceField('bill_to_address', e.target.value)}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="bill_to_gstin">GSTIN</label>
                    <input
                      id="bill_to_gstin"
                      type="text"
                      value={invoiceForm.bill_to_gstin}
                      onChange={(e) => updateInvoiceField('bill_to_gstin', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="bill_to_email">Email</label>
                    <input
                      id="bill_to_email"
                      type="email"
                      value={invoiceForm.bill_to_email}
                      onChange={(e) => updateInvoiceField('bill_to_email', e.target.value)}
                    />
                  </div>
                </div>
              </fieldset>

              <div className="invoice-line-items">
                <div className="invoice-line-items-header">
                  <h3>Line items</h3>
                  <button type="button" className="admin-action-btn" onClick={addInvoiceLineItem}>
                    + Add line
                  </button>
                </div>
                {invoiceForm.line_items.map((item, idx) => (
                  <div className="invoice-line-item" key={`invoice-line-${idx}`}>
                    <div className="form-group">
                      <label htmlFor={`line_desc_${idx}`}>Description</label>
                      <textarea
                        id={`line_desc_${idx}`}
                        rows={3}
                        value={item.description}
                        onChange={(e) => updateInvoiceLineItem(idx, 'description', e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor={`line_rate_${idx}`}>Rate (USD)</label>
                        <input
                          id={`line_rate_${idx}`}
                          type="number"
                          min="0"
                          step="0.01"
                          value={item.rate}
                          onChange={(e) => updateInvoiceLineItem(idx, 'rate', e.target.value)}
                          required
                        />
                      </div>
                      <div className="form-group">
                        <label htmlFor={`line_rate_label_${idx}`}>Rate label</label>
                        <input
                          id={`line_rate_label_${idx}`}
                          type="text"
                          placeholder="$22 / Task"
                          value={item.rate_label}
                          onChange={(e) => updateInvoiceLineItem(idx, 'rate_label', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor={`line_qty_${idx}`}>Quantity</label>
                        <input
                          id={`line_qty_${idx}`}
                          type="number"
                          min="0"
                          step="0.01"
                          value={item.quantity}
                          onChange={(e) => updateInvoiceLineItem(idx, 'quantity', e.target.value)}
                          required
                        />
                      </div>
                      <div className="form-group">
                        <label htmlFor={`line_qty_label_${idx}`}>Quantity label</label>
                        <input
                          id={`line_qty_label_${idx}`}
                          type="text"
                          placeholder="10 task"
                          value={item.quantity_label}
                          onChange={(e) => updateInvoiceLineItem(idx, 'quantity_label', e.target.value)}
                        />
                      </div>
                    </div>
                    {invoiceForm.line_items.length > 1 ? (
                      <button
                        type="button"
                        className="admin-action-btn danger invoice-remove-line"
                        onClick={() => removeInvoiceLineItem(idx)}
                      >
                        Remove line
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>

              {invoiceError && (
                <div className="error-message" role="alert">
                  <strong>Error:</strong> {invoiceError}
                </div>
              )}

              <button
                type="submit"
                className="download-btn cert-submit-btn"
                disabled={isGeneratingInvoice}
              >
                {isGeneratingInvoice ? <Icon.Loader /> : <Icon.Invoice />}
                <span>{isGeneratingInvoice ? 'Generating...' : 'Generate invoice PDF'}</span>
              </button>
            </form>

            {invoiceResult && (
              <div className="cert-result">
                <div className="cert-result-header">
                  <span className="cert-result-check"><Icon.CheckCircle /></span>
                  Invoice <strong>{invoiceResult.invoice_number}</strong> ready
                  <span className="cert-id-badge">{invoiceResult.total_inr_formatted}</span>
                </div>
                <p className="invoice-result-words">{invoiceResult.amount_in_words}</p>
                <div className="cert-result-actions">
                  <button
                    className="download-btn cert-action-btn"
                    onClick={downloadInvoicePdf}
                    type="button"
                  >
                    <Icon.Download />
                    <span>Download PDF</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="cert-preview-section">
            <div className="section-header">
              <h2>Invoice Preview</h2>
            </div>
            <div className="cert-preview invoice-preview">
              <InvoicePreviewCard
                invoiceForm={invoiceForm}
                invoiceResult={invoiceResult}
                invoiceBrand={invoiceBrand}
              />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'admin' && (
        <div className="admin-container">
          <AdminDashboard getApiUrl={getApiUrl} />
        </div>
      )}

      <footer className="footer">
        <div className="footer-brand">
          <CertIcon size={22} />
          <span className="footer-brand-name">{branding.brand_name}</span>
        </div>
        <p className="footer-tagline">
          API-first PDF certificate generation
        </p>
        <p className="footer-copy">
          Built with React, Vite, FastAPI & Python
        </p>
      </footer>
    </div>
  )
}

export default App
