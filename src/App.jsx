import { useState, useEffect, useId } from 'react'
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
          instructor_name: instrIdx >= 0 ? cols[instrIdx]?.trim() || 'IntelliForge AI Team' : 'IntelliForge AI Team',
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

  const getApiUrl = (path) =>
    import.meta.env.PROD ? path : `http://localhost:8000${path}`

  useEffect(() => {
    fetch(getApiUrl('/api/courses'))
      .then((res) => res.json())
      .then((data) => setCourses(data.courses || []))
      .catch(() => setCourses([]))
      .finally(() => setCoursesLoading(false))
  }, [])

  const [certForm, setCertForm] = useState({
    participant_name: '',
    participant_email: '',
    course_name: '',
    completion_date: new Date().toISOString().split('T')[0],
    instructor_name: 'IntelliForge AI Team',
  })
  const [isGenerating, setIsGenerating] = useState(false)
  const [certError, setCertError] = useState(null)
  const [certResult, setCertResult] = useState(null)

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
        <h1>IntelliForge Certificates</h1>
        <p className="header-subtitle">
          Issue verified training certificates, share links, and manage courses from one place
        </p>
        <nav className="tab-nav" role="tablist">
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
                <label htmlFor="participant_email">Participant Email <span className="form-optional">(optional – certificate will be emailed)</span></label>
                <input
                  id="participant_email"
                  type="email"
                  placeholder="e.g. jane@example.com"
                  value={certForm.participant_email}
                  onChange={(e) => updateCertField('participant_email', e.target.value)}
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
                {certResult.email_sent && (
                  <div className="cert-email-sent">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                    Certificate emailed to {certForm.participant_email}
                  </div>
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
                <div className="cert-header">
                  <span className="cert-header-org">An IntelliForge AI Initiative</span>
                  <span className="cert-header-brand">IntelliForge Learning</span>
                  <span className="cert-header-badge">Certificate of Participation</span>
                </div>
                <div className="cert-body">
                  <div className="cert-verified">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="14" height="14"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                    Verified &amp; Authentic
                  </div>
                  <p className="cert-award-label">This Certificate is Awarded To</p>
                  <p className="cert-name">
                    {certForm.participant_name || 'Participant Name'}
                  </p>
                  <div className="cert-gold-divider" />
                  <p className="cert-course">
                    {certForm.course_name || 'Select a course'}
                  </p>
                  <div className="cert-meta-row">
                    <div className="cert-meta-item">
                      <span className="cert-meta-value">{certForm.completion_date || '\u2014'}</span>
                      <span className="cert-meta-label">Date</span>
                    </div>
                    <div className="cert-meta-item cert-meta-bordered">
                      <span className="cert-meta-value">{certForm.instructor_name || 'IntelliForge AI Team'}</span>
                      <span className="cert-meta-label">Instructor</span>
                    </div>
                    <div className="cert-meta-item">
                      <span className="cert-meta-value cert-meta-id">IF-XXXXXXXXXXXX</span>
                      <span className="cert-meta-label">Certificate ID</span>
                    </div>
                  </div>
                  <div className="cert-signatures">
                    <div className="cert-sig-block">
                      <span className="cert-sig-hand">Girish Hiremath</span>
                      <span className="cert-sig-line" />
                      <span className="cert-sig-name">Girish Hiremath</span>
                      <span className="cert-sig-role">Founder &amp; CEO, IntelliForge AI</span>
                    </div>
                    <div className="cert-sig-block">
                      <span className="cert-sig-hand">
                        {certForm.instructor_name || 'IntelliForge AI Team'}
                      </span>
                      <span className="cert-sig-line" />
                      <span className="cert-sig-name">
                        {certForm.instructor_name || 'IntelliForge AI Team'}
                      </span>
                      <span className="cert-sig-role">Course Instructor</span>
                    </div>
                  </div>
                  <div className="cert-qr-placeholder">
                    <div className="cert-qr-box">QR</div>
                    <div className="cert-qr-text">
                      <strong>Scan to Verify</strong>
                      QR code links to the permanent verification page.
                    </div>
                  </div>
                </div>
                <div className="cert-footer-bar">
                  Issued by IntelliForge Learning &middot; learning.intelliforge.tech &middot; support@intelliforge.tech
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
