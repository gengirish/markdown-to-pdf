import { useState } from 'react'
import { marked } from 'marked'
import './App.css'

const COURSES = [
  "AI Product Development Fundamentals",
  "Building AI-Powered Applications",
  "Prompt Engineering & LLM Integration",
  "Full-Stack AI Development",
  "AI Product Design & UX",
  "Digital Profile Creation",
  "Deploying AI Solutions",
  "AI Code Reviewer Course",
]

const Icon = {
  FileText: () => (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  ),
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
  Markdown: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  ),
  CertTab: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="7" />
      <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
    </svg>
  ),
}

function App() {
  const [activeTab, setActiveTab] = useState('markdown')

  const [markdown, setMarkdown] = useState(`# Welcome to Markdown to PDF Converter

## Features
- Real-time markdown preview
- Server-side PDF generation with Python
- FastAPI backend for robust processing
- Beautiful, modern UI

## How to use
1. Type or paste your markdown in the left panel
2. See the live preview in the right panel
3. Click "Download PDF" to export

### Sample Code Block
\`\`\`javascript
const hello = () => {
  console.log("Hello, World!");
};
\`\`\`

### Sample List
- Item 1
- Item 2
- Item 3

**Bold text** and *italic text* are supported!

> This is a blockquote with professional styling

---

### Technical Details
This application uses:
- **Frontend**: React + Vite
- **Backend**: FastAPI + Python
- **PDF Engine**: xhtml2pdf
- **Deployment**: Vercel

Enjoy converting your markdown!`)

  const [isConverting, setIsConverting] = useState(false)
  const [error, setError] = useState(null)

  const [certForm, setCertForm] = useState({
    participant_name: '',
    course_name: '',
    completion_date: new Date().toISOString().split('T')[0],
    instructor_name: 'IntelliForge AI Team',
  })
  const [isGenerating, setIsGenerating] = useState(false)
  const [certError, setCertError] = useState(null)
  const [certResult, setCertResult] = useState(null)

  const getApiUrl = (path) =>
    import.meta.env.PROD ? path : `http://localhost:8000${path}`

  const convertToPdf = async () => {
    setIsConverting(true)
    setError(null)

    try {
      const response = await fetch(getApiUrl('/api/convert'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown, filename: 'markdown-export.pdf' }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'markdown-export.pdf'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Error converting to PDF:', err)
      setError(err.message)
    } finally {
      setIsConverting(false)
    }
  }

  const generateCertificate = async (e) => {
    e.preventDefault()
    setIsGenerating(true)
    setCertError(null)
    setCertResult(null)

    try {
      if (!certForm.participant_name.trim()) throw new Error('Please enter participant name')
      if (!certForm.course_name) throw new Error('Please select a course')
      if (!certForm.completion_date) throw new Error('Please select a date')

      const response = await fetch(getApiUrl('/api/certificate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(certForm),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }

      const data = await response.json()
      setCertResult(data)
    } catch (err) {
      console.error('Error generating certificate:', err)
      setCertError(err.message)
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
      a.download = `Certificate_${certResult.participant_name.replace(/\s+/g, '_')}.pdf`
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

  return (
    <div className="app">
      <header className="header">
        <div className="header-icon">
          <Icon.FileText />
        </div>
        <h1>Markdown to PDF</h1>
        <p>Convert markdown to PDF & generate participation certificates</p>
        <nav className="tab-nav" role="tablist">
          <button
            className={`tab-btn ${activeTab === 'markdown' ? 'active' : ''}`}
            onClick={() => setActiveTab('markdown')}
            role="tab"
            aria-selected={activeTab === 'markdown'}
          >
            <Icon.Markdown />
            <span>Markdown to PDF</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'certificate' ? 'active' : ''}`}
            onClick={() => setActiveTab('certificate')}
            role="tab"
            aria-selected={activeTab === 'certificate'}
          >
            <Icon.CertTab />
            <span>Certificate Generator</span>
          </button>
        </nav>
      </header>

      {activeTab === 'markdown' && (
        <div className="container">
          <div className="editor-section">
            <div className="section-header">
              <h2>Markdown Editor</h2>
              <span className="char-count">{markdown.length} chars</span>
            </div>
            <textarea
              className="editor"
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              placeholder="Type your markdown here..."
              spellCheck="false"
              aria-label="Markdown editor"
            />
          </div>

          <div className="preview-section">
            <div className="section-header">
              <h2>Live Preview</h2>
              <button
                className="download-btn"
                onClick={convertToPdf}
                disabled={isConverting}
              >
                {isConverting ? <Icon.Loader /> : <Icon.Download />}
                <span>{isConverting ? 'Converting...' : 'Download PDF'}</span>
              </button>
            </div>
            {error && (
              <div className="error-message" role="alert">
                <strong>Error:</strong> {error}
              </div>
            )}
            <div
              className="preview"
              dangerouslySetInnerHTML={{ __html: marked(markdown) }}
            />
          </div>
        </div>
      )}

      {activeTab === 'certificate' && (
        <div className="cert-container">
          <div className="cert-form-section">
            <div className="section-header">
              <h2>Certificate Details</h2>
            </div>
            <form className="cert-form" onSubmit={generateCertificate}>
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
                <label htmlFor="course_name">Training Course</label>
                <select
                  id="course_name"
                  value={certForm.course_name}
                  onChange={(e) => updateCertField('course_name', e.target.value)}
                  required
                >
                  <option value="">Select a course</option>
                  {COURSES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

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
                <div className="form-group">
                  <label htmlFor="instructor_name">Instructor Name</label>
                  <input
                    id="instructor_name"
                    type="text"
                    placeholder="IntelliForge AI Team"
                    value={certForm.instructor_name}
                    onChange={(e) => updateCertField('instructor_name', e.target.value)}
                  />
                </div>
              </div>

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
                <span>{isGenerating ? 'Generating...' : 'Generate Certificate'}</span>
              </button>
            </form>

            {certResult && (
              <div className="cert-result">
                <div className="cert-result-header">
                  <span className="cert-result-check"><Icon.CheckCircle /></span>
                  Certificate issued for <strong>{certResult.participant_name}</strong>
                  <span className="cert-id-badge">{certResult.certificate_id}</span>
                </div>

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
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`I completed ${certResult.course_name} at IntelliForge Learning!`)}&url=${encodeURIComponent(certResult.url)}`}
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
              <div className="cert-card">
                <div className="cert-card-border">
                  <p className="cert-logo-line">An IntelliForge AI Initiative</p>
                  <p className="cert-org">IntelliForge Learning</p>
                  <h3 className="cert-title">CERTIFICATE</h3>
                  <p className="cert-subtitle">of Participation</p>
                  <p className="cert-presented">This is proudly presented to</p>
                  <p className="cert-name">
                    {certForm.participant_name || 'Participant Name'}
                  </p>
                  <p className="cert-desc">
                    For successfully participating in the training program
                    <br />
                    <strong>{certForm.course_name || 'Select a course'}</strong>
                    <br />
                    conducted by IntelliForge Learning
                  </p>
                  <div className="cert-details">
                    <div>
                      <span className="cert-detail-value">
                        {certForm.completion_date || '\u2014'}
                      </span>
                      <span className="cert-detail-label">Date</span>
                    </div>
                    <div>
                      <span className="cert-detail-value">
                        {certForm.instructor_name || 'IntelliForge AI Team'}
                      </span>
                      <span className="cert-detail-label">Instructor</span>
                    </div>
                    <div>
                      <span className="cert-detail-value">
                        learning.intelliforge.tech
                      </span>
                      <span className="cert-detail-label">Platform</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <footer className="footer">
        <p>
          Built with React, Vite, FastAPI & Python
          <span className="footer-divider">|</span>
          <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener noreferrer">
            IntelliForge Learning
          </a>
        </p>
      </footer>
    </div>
  )
}

export default App
