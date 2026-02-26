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
]

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

Enjoy converting your markdown! 🎉`)

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
  const [certSuccess, setCertSuccess] = useState(false)

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
    setCertSuccess(false)

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

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Certificate_${certForm.participant_name.replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      setCertSuccess(true)
    } catch (err) {
      console.error('Error generating certificate:', err)
      setCertError(err.message)
    } finally {
      setIsGenerating(false)
    }
  }

  const updateCertField = (field, value) => {
    setCertForm((prev) => ({ ...prev, [field]: value }))
    setCertError(null)
    setCertSuccess(false)
  }

  return (
    <div className="app">
      <header className="header">
        <h1>📄 Markdown to PDF Converter</h1>
        <p>Convert markdown to PDF &amp; generate participation certificates</p>
        <nav className="tab-nav">
          <button
            className={`tab-btn ${activeTab === 'markdown' ? 'active' : ''}`}
            onClick={() => setActiveTab('markdown')}
          >
            Markdown to PDF
          </button>
          <button
            className={`tab-btn ${activeTab === 'certificate' ? 'active' : ''}`}
            onClick={() => setActiveTab('certificate')}
          >
            Certificate Generator
          </button>
        </nav>
      </header>

      {activeTab === 'markdown' && (
        <div className="container">
          <div className="editor-section">
            <div className="section-header">
              <h2>Markdown Editor</h2>
              <span className="char-count">{markdown.length} characters</span>
            </div>
            <textarea
              className="editor"
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              placeholder="Type your markdown here..."
              spellCheck="false"
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
                {isConverting ? '⏳ Converting...' : '⬇ Download PDF'}
              </button>
            </div>
            {error && (
              <div className="error-message">
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
                <label htmlFor="participant_name">Participant Name *</label>
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
                <label htmlFor="course_name">Training Course *</label>
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
                  <label htmlFor="completion_date">Completion Date *</label>
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
                <div className="error-message">
                  <strong>Error:</strong> {certError}
                </div>
              )}
              {certSuccess && (
                <div className="success-message">
                  Certificate downloaded successfully!
                </div>
              )}

              <button
                type="submit"
                className="download-btn cert-submit-btn"
                disabled={isGenerating}
              >
                {isGenerating ? '⏳ Generating...' : '🎓 Generate Certificate PDF'}
              </button>
            </form>
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
                        {certForm.completion_date || '—'}
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
          Built with React, Vite, FastAPI &amp; Python
          &nbsp;|&nbsp;
          <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener noreferrer">
            IntelliForge Learning
          </a>
        </p>
      </footer>
    </div>
  )
}

export default App
