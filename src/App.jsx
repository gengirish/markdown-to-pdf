import { useState, useEffect, useId } from 'react'
import { marked } from 'marked'
import './App.css'

function IntelliForgeIcon({ size = 32 }) {
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
  Admin: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  ),
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
  const [activeTab, setActiveTab] = useState('markdown')
  const [courses, setCourses] = useState([])
  const [coursesLoading, setCoursesLoading] = useState(true)

  const getApiUrl = (path) =>
    import.meta.env.PROD ? path : `http://localhost:8000${path}`

  useEffect(() => {
    fetch(getApiUrl('/api/courses'))
      .then((res) => res.json())
      .then((data) => setCourses(data.courses || []))
      .catch(() => setCourses([]))
      .finally(() => setCoursesLoading(false))
  }, [])

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
        <a
          href="https://www.intelliforge.tech/"
          target="_blank"
          rel="noopener noreferrer"
          className="brand-link"
          aria-label="IntelliForge AI"
        >
          <div className="header-icon">
            <IntelliForgeIcon size={32} />
          </div>
          <span className="brand-wordmark">IntelliForge AI</span>
        </a>
        <h1>Markdown to PDF</h1>
        <p className="header-subtitle">
          Real-time markdown editor with live preview & certificate generation
        </p>
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
                  disabled={coursesLoading}
                >
                  <option value="">{coursesLoading ? 'Loading courses...' : 'Select a course'}</option>
                  {courses.map((c) => (
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

      {activeTab === 'admin' && (
        <div className="admin-container">
          <AdminDashboard getApiUrl={getApiUrl} />
        </div>
      )}

      <footer className="footer">
        <div className="footer-brand">
          <IntelliForgeIcon size={22} />
          <span className="footer-brand-name">IntelliForge AI</span>
        </div>
        <p className="footer-tagline">
          AI Agent Development & Workflow Automation
        </p>
        <div className="footer-links">
          <a href="https://www.intelliforge.tech/" target="_blank" rel="noopener noreferrer">
            intelliforge.tech
          </a>
          <span className="footer-divider" aria-hidden="true" />
          <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener noreferrer">
            IntelliForge Learning
          </a>
          <span className="footer-divider" aria-hidden="true" />
          <a href="https://www.intelliforge.tech/services" target="_blank" rel="noopener noreferrer">
            Services
          </a>
        </div>
        <p className="footer-copy">
          Built with React, Vite, FastAPI & Python
        </p>
      </footer>
    </div>
  )
}

export default App
