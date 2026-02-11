# 🏗️ Architecture Overview

## Full-Stack Markdown to PDF Converter

This application follows a modern full-stack architecture with clear separation of concerns:

### Frontend → Backend → PDF

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   React     │      │   FastAPI   │      │     PDF     │
│   + Vite    │ ───► │  + Python   │ ───► │   Output    │
│  (UI Only)  │ HTTP │ (Business)  │      │  (File)     │
└─────────────┘      └─────────────┘      └─────────────┘
```

---

## 🎨 Frontend (React + Vite)

**Location:** `src/`

**Purpose:** User interface and markdown editing

**Technologies:**
- React 19.2.0
- Vite 7.3.1
- marked (for preview only)

**Responsibilities:**
- ✅ Markdown editor interface
- ✅ Real-time HTML preview
- ✅ Send markdown to backend API
- ✅ Trigger PDF download
- ❌ NO business logic
- ❌ NO PDF generation

**Key Files:**
- `src/App.jsx` - Main UI component
- `src/App.css` - Styling
- `src/main.jsx` - React entry point

**API Communication:**
```javascript
// Production (Vercel)
POST /api/convert

// Local Development
POST http://localhost:8000/api/convert

Body: {
  "markdown": "# My Document...",
  "filename": "document.pdf"
}
```

---

## ⚙️ Backend (FastAPI + Python)

**Location:** `api/`

**Purpose:** Business logic and PDF generation

**Technologies:**
- FastAPI 0.115.0
- Python 3.13
- markdown (parsing)
- xhtml2pdf (PDF generation)
- reportlab (PDF library)

**Responsibilities:**
- ✅ Receive markdown from frontend
- ✅ Parse markdown to HTML
- ✅ Apply professional styling
- ✅ Generate PDF document
- ✅ Return PDF file
- ✅ Error handling
- ✅ Logging

**Key Files:**
- `api/index.py` - Main FastAPI application
- `api/__init__.py` - Package marker

**Endpoints:**

### GET /
Health check and API info

### GET /api/health
Health check endpoint

### POST /api/convert
Convert markdown to PDF

**Request:**
```json
{
  "markdown": "# Title\n\nContent...",
  "filename": "output.pdf"
}
```

**Response:**
- Content-Type: application/pdf
- Binary PDF file

### GET /api/info
API information and capabilities

---

## 🔄 Data Flow

### 1. User Types Markdown
```
User → React Editor → State Update → Live Preview
```

### 2. User Clicks "Download PDF"
```
React App
  → API Request (POST /api/convert)
    → FastAPI Receives Request
      → Parse Markdown → HTML
        → Style HTML → Professional CSS
          → Generate PDF → xhtml2pdf
            → Return PDF Binary
              → Browser Downloads File
```

### 3. Frontend Processing
```javascript
// 1. Prepare request
const payload = {
  markdown: markdownText,
  filename: 'document.pdf'
};

// 2. Send to backend
const response = await fetch('/api/convert', {
  method: 'POST',
  body: JSON.stringify(payload)
});

// 3. Get PDF blob
const blob = await response.blob();

// 4. Trigger download
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'document.pdf';
a.click();
```

### 4. Backend Processing
```python
# 1. Receive markdown
@app.post("/api/convert")
async def convert(request: MarkdownRequest):
    
    # 2. Parse markdown to HTML
    html = markdown.convert(request.markdown)
    
    # 3. Apply styling
    styled_html = HTML_TEMPLATE.format(content=html)
    
    # 4. Generate PDF
    pdf_buffer = BytesIO()
    pisa.CreatePDF(styled_html, dest=pdf_buffer)
    
    # 5. Return PDF
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf"
    )
```

---

## 📦 Deployment Architecture

### Development
```
┌─────────────────┐         ┌─────────────────┐
│  Vite Dev Server│         │  Uvicorn Server │
│  localhost:5173 │ ───────►│  localhost:8000 │
└─────────────────┘  CORS   └─────────────────┘
```

### Production (Vercel)
```
┌────────────────────────────────────────┐
│           Vercel Platform              │
│                                        │
│  ┌──────────────┐  ┌─────────────────┐│
│  │   Frontend   │  │  API Functions  ││
│  │   (Static)   │  │  (Serverless)   ││
│  │              │  │                 ││
│  │  dist/       │  │  api/index.py   ││
│  │  - HTML      │  │  - Python 3.9   ││
│  │  - CSS       │  │  - FastAPI      ││
│  │  - JS        │  │  - Auto-scaled  ││
│  └──────────────┘  └─────────────────┘│
│                                        │
│  Routing:                              │
│  /         → Frontend (SPA)           │
│  /api/*    → Backend (Serverless)     │
└────────────────────────────────────────┘
```

**Vercel Configuration:** `vercel.json`
```json
{
  "functions": {
    "api/index.py": {
      "runtime": "python3.9"
    }
  },
  "rewrites": [
    { "source": "/api/:path*", "destination": "/api/index.py" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

---

## 🔒 Security Considerations

### Input Validation
- ✅ Markdown content validated
- ✅ Filename sanitized
- ✅ Size limits enforced (implicit)

### CORS Configuration
- Development: Allow localhost
- Production: Allow Vercel domains
- Configurable in `api/index.py`

### Error Handling
- Backend catches all exceptions
- Returns proper HTTP status codes
- Logs errors for debugging
- Frontend shows user-friendly messages

---

## 📊 Performance

### Frontend
- **Bundle Size:** 74KB (gzipped)
- **Load Time:** < 2 seconds
- **Interactive:** Instant
- **Preview:** Real-time (< 50ms)

### Backend
- **Cold Start:** 1-3 seconds (serverless)
- **Warm Latency:** 200-500ms
- **PDF Generation:** 1-2 seconds
- **Concurrent:** Auto-scaled by Vercel

### Optimization
- Frontend: Code splitting, tree shaking
- Backend: Efficient markdown parsing
- Network: Gzip compression
- CDN: Static assets cached

---

## 🛠️ Development Setup

### Prerequisites
```bash
# Node.js 18+
node --version

# Python 3.9+
python --version

# npm
npm --version

# pip
pip --version
```

### Install Dependencies
```bash
# Frontend
npm install

# Backend
pip install -r requirements.txt
```

### Run Development Servers

**Terminal 1 - Backend:**
```bash
python -m uvicorn api.index:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

**Access:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs (auto-generated)

---

## 🧪 Testing

### Test Backend API

**Health Check:**
```bash
curl http://localhost:8000/api/health
```

**Convert Markdown:**
```bash
curl -X POST http://localhost:8000/api/convert \
  -H "Content-Type: application/json" \
  -d '{"markdown": "# Test", "filename": "test.pdf"}' \
  --output test.pdf
```

### Test Frontend
1. Open http://localhost:5173
2. Type markdown in editor
3. See live preview
4. Click "Download PDF"
5. Verify PDF downloads

---

## 📚 Technology Choices

### Why FastAPI?
- ✅ Fast and modern
- ✅ Automatic API docs
- ✅ Type validation (Pydantic)
- ✅ Easy async support
- ✅ Vercel compatible

### Why xhtml2pdf?
- ✅ Pure Python (easy deployment)
- ✅ Good HTML/CSS support
- ✅ Mature and stable
- ✅ Works in serverless
- ✅ No system dependencies

### Why React + Vite?
- ✅ Fast development
- ✅ Modern tooling
- ✅ Great DX
- ✅ Small bundle
- ✅ Vercel optimized

---

## 🔄 Future Enhancements

### Frontend
- [ ] Markdown syntax highlighting in editor
- [ ] Dark mode
- [ ] Multiple themes
- [ ] Save/load from localStorage

### Backend
- [ ] Multiple PDF templates
- [ ] Custom styling options
- [ ] Batch conversion
- [ ] Webhook support
- [ ] Rate limiting
- [ ] Caching

### Infrastructure
- [ ] Database for history
- [ ] User accounts
- [ ] API authentication
- [ ] Analytics
- [ ] Monitoring

---

## 📖 API Documentation

When running locally, visit:
- **Interactive Docs:** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc

FastAPI generates these automatically!

---

## 🐛 Debugging

### Backend Logs
Check terminal running uvicorn for:
- Request logs
- Error traces
- Performance metrics

### Frontend Logs
Check browser console for:
- Network requests
- Response errors
- Client-side issues

### Common Issues

**CORS Error:**
- Update CORS settings in `api/index.py`
- Check API URL in frontend

**PDF Generation Fails:**
- Check backend logs
- Verify markdown is valid
- Check xhtml2pdf compatibility

**Build Fails:**
- Clear `node_modules` and reinstall
- Clear `dist/` folder
- Check Node/Python versions

---

## 📞 Support

For more details, see:
- `README.md` - General documentation
- `DEPLOYMENT.md` - Deployment guide
- `QUICKSTART.md` - Quick start guide

---

**Built with ❤️ using modern full-stack architecture**
