import { useState, useRef } from 'react'
import { marked } from 'marked'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import './App.css'

function App() {
  const [markdown, setMarkdown] = useState(`# Welcome to Markdown to PDF Converter

## Features
- Real-time markdown preview
- Live HTML rendering
- Export to PDF with one click
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

> This is a blockquote

---

Enjoy converting your markdown! 🎉`)

  const [isConverting, setIsConverting] = useState(false)
  const previewRef = useRef(null)

  const convertToPdf = async () => {
    if (!previewRef.current) return
    
    setIsConverting(true)
    
    try {
      // Create canvas from the preview content
      const canvas = await html2canvas(previewRef.current, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff'
      })
      
      const imgData = canvas.toDataURL('image/png')
      
      // Calculate dimensions
      const imgWidth = 210 // A4 width in mm
      const pageHeight = 297 // A4 height in mm
      const imgHeight = (canvas.height * imgWidth) / canvas.width
      let heightLeft = imgHeight
      
      const pdf = new jsPDF('p', 'mm', 'a4')
      let position = 0
      
      // Add first page
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
      
      // Add additional pages if content is longer than one page
      while (heightLeft >= 0) {
        position = heightLeft - imgHeight
        pdf.addPage()
        pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
        heightLeft -= pageHeight
      }
      
      pdf.save('markdown-export.pdf')
    } catch (error) {
      console.error('Error converting to PDF:', error)
      alert('Error converting to PDF. Please try again.')
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
              {isConverting ? 'Converting...' : '⬇ Download PDF'}
            </button>
          </div>
          <div 
            ref={previewRef}
            className="preview"
            dangerouslySetInnerHTML={getHtmlFromMarkdown()}
          />
        </div>
      </div>
      
      <footer className="footer">
        <p>Built with React, Vite, marked, jsPDF & html2canvas</p>
      </footer>
    </div>
  )
}

export default App
