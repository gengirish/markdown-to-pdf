import { useState } from 'react'
import { marked } from 'marked'
import './App.css'

function App() {
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
- **PDF Engine**: WeasyPrint
- **Deployment**: Vercel

Enjoy converting your markdown! 🎉`)

  const [isConverting, setIsConverting] = useState(false)
  const [error, setError] = useState(null)

  const convertToPdf = async () => {
    setIsConverting(true)
    setError(null)
    
    try {
      // Determine API URL based on environment
      const apiUrl = import.meta.env.PROD 
        ? '/api/convert'  // Production (Vercel)
        : 'http://localhost:8000/api/convert'  // Local development
      
      // Send markdown to backend API
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          markdown: markdown,
          filename: 'markdown-export.pdf'
        })
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }
      
      // Get PDF blob from response
      const blob = await response.blob()
      
      // Create download link and trigger download
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'markdown-export.pdf'
      document.body.appendChild(a)
      a.click()
      
      // Cleanup
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      
    } catch (error) {
      console.error('Error converting to PDF:', error)
      setError(error.message)
      alert(`Error converting to PDF: ${error.message}`)
    } finally {
      setIsConverting(false)
    }
  }

  const handleMarkdownChange = (e) => {
    setMarkdown(e.target.value)
  }

  const getHtmlFromMarkdown = () => {
    return { __html: marked(markdown) }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>📄 Markdown to PDF Converter</h1>
        <p>Convert your markdown to beautifully formatted PDFs</p>
      </header>
      
      <div className="container">
        <div className="editor-section">
          <div className="section-header">
            <h2>Markdown Editor</h2>
            <span className="char-count">{markdown.length} characters</span>
          </div>
          <textarea
            className="editor"
            value={markdown}
            onChange={handleMarkdownChange}
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
            dangerouslySetInnerHTML={getHtmlFromMarkdown()}
          />
        </div>
      </div>
      
      <footer className="footer">
        <p>Built with React, Vite, FastAPI, Python & WeasyPrint</p>
      </footer>
    </div>
  )
}

export default App
