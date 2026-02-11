# 👨‍💻 Development Guide

## Getting Started with Development

This guide will help you set up and develop the Markdown to PDF Converter locally.

---

## 📋 Prerequisites

### Required Software

1. **Node.js** (v18 or higher)
   ```bash
   node --version  # Should show v18.x or higher
   ```

2. **Python** (v3.9 or higher)
   ```bash
   python --version  # Should show 3.9.x or higher
   ```

3. **npm** (comes with Node.js)
   ```bash
   npm --version
   ```

4. **pip** (comes with Python)
   ```bash
   pip --version
   ```

---

## 🚀 Setup

### 1. Install Frontend Dependencies

```bash
npm install
```

This installs:
- React
- Vite
- marked (for markdown preview)

### 2. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- FastAPI
- uvicorn
- markdown
- xhtml2pdf
- reportlab
- pydantic

---

## 💻 Running the Application

You need **TWO** terminal windows:

### Terminal 1: Backend Server

```bash
# Start FastAPI backend on port 8000
python -m uvicorn api.index:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Started reloader process
```

### Terminal 2: Frontend Server

```bash
# Start Vite dev server on port 5173
npm run dev
```

You should see:
```
VITE v7.3.1  ready in X ms
➜  Local:   http://localhost:5173/
```

### 3. Open the Application

Open your browser to: **http://localhost:5173**

---

## 🧪 Testing the Application

### Manual Testing

1. **Type markdown** in the left editor
2. **See live preview** on the right
3. **Click "Download PDF"** button
4. **Verify** PDF downloads and opens correctly

### Test the Backend API

#### Health Check
```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "status": "healthy",
  "service": "markdown-to-pdf",
  "version": "1.0.0"
}
```

#### API Info
```bash
curl http://localhost:8000/api/info
```

#### Convert Markdown
```bash
curl -X POST http://localhost:8000/api/convert \
  -H "Content-Type: application/json" \
  -d '{"markdown": "# Hello World\n\nThis is a **test** document."}' \
  --output test.pdf
```

### Interactive API Documentation

FastAPI generates automatic API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These allow you to test the API interactively!

---

## 📁 Project Structure

```
tool/
├── api/                        # Backend (Python/FastAPI)
│   ├── __init__.py            # Package marker
│   └── index.py               # Main FastAPI app
│
├── src/                        # Frontend (React/Vite)
│   ├── App.jsx                # Main React component
│   ├── App.css                # Styles
│   ├── main.jsx               # React entry point
│   └── index.css              # Global styles
│
├── public/                     # Static assets
├── dist/                       # Production build (generated)
│
├── requirements.txt            # Python dependencies
├── package.json               # Node dependencies
├── vercel.json                # Vercel deployment config
├── vite.config.js             # Vite configuration
│
└── Documentation/
    ├── README.md              # Main docs
    ├── ARCHITECTURE.md        # System architecture
    ├── DEVELOPMENT.md         # This file
    ├── DEPLOYMENT.md          # Deployment guide
    └── QUICKSTART.md          # Quick start
```

---

## 🔧 Development Workflow

### Making Changes

#### Frontend Changes
1. Edit files in `src/`
2. Save the file
3. Vite will auto-reload the browser
4. See changes immediately

#### Backend Changes
1. Edit `api/index.py`
2. Save the file
3. Uvicorn will auto-reload
4. Test in browser or with curl

### Building for Production

```bash
# Build frontend
npm run build

# Test production build locally
npm run preview
```

---

## 🎨 Customizing Styles

### Frontend Styles

Edit `src/App.css`:

```css
/* Change colors */
.app {
  background: linear-gradient(135deg, #your-color 0%, #another-color 100%);
}

/* Modify editor */
.editor {
  font-size: 16px;
  background: #your-bg-color;
}

/* Update preview */
.preview {
  font-family: 'Your Font', sans-serif;
}
```

### PDF Styles

Edit `api/index.py` → `HTML_TEMPLATE`:

```python
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            font-family: 'Your Font', sans-serif;
            color: #your-color;
        }
        /* Add your custom styles */
    </style>
</head>
<body>{content}</body>
</html>
"""
```

---

## 📝 Adding Features

### Frontend Feature Example

```javascript
// In App.jsx
const [newFeature, setNewFeature] = useState(false);

// Add button
<button onClick={() => setNewFeature(true)}>
  Enable Feature
</button>
```

### Backend Feature Example

```python
# In api/index.py

@app.post("/api/new-feature")
async def new_feature(data: NewFeatureRequest):
    """New feature endpoint"""
    # Your logic here
    return {"result": "success"}
```

---

## 🐛 Debugging

### Frontend Debugging

**Browser Console:**
```javascript
// Add console logs in App.jsx
console.log('Markdown:', markdown);
console.log('API Response:', response);
```

**React DevTools:**
- Install React DevTools browser extension
- Inspect component state and props

### Backend Debugging

**Python Logging:**
```python
# In api/index.py
logger.info(f"Received markdown: {request.markdown[:100]}")
logger.error(f"Error: {str(e)}")
```

**FastAPI Debugging:**
```python
import pdb; pdb.set_trace()  # Breakpoint
```

**View Logs:**
Check the terminal running uvicorn

---

## 🔍 Common Issues

### Port Already in Use

```bash
# Kill process on port 5173 (frontend)
npx kill-port 5173

# Kill process on port 8000 (backend)
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Mac/Linux:
lsof -ti:8000 | xargs kill -9
```

### CORS Errors

Update `api/index.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Module Not Found

```bash
# Reinstall Python dependencies
pip install -r requirements.txt

# Reinstall Node dependencies
rm -rf node_modules package-lock.json
npm install
```

### PDF Generation Fails

Check backend logs for:
- Invalid markdown syntax
- Missing dependencies
- xhtml2pdf errors

---

## 📦 Dependencies Management

### Update Frontend Dependencies

```bash
# Check for updates
npm outdated

# Update specific package
npm update marked

# Update all
npm update
```

### Update Backend Dependencies

```bash
# Check for updates
pip list --outdated

# Update specific package
pip install --upgrade fastapi

# Update all
pip install --upgrade -r requirements.txt
```

---

## 🧪 Testing Checklist

Before committing changes:

- [ ] Frontend builds successfully (`npm run build`)
- [ ] Backend starts without errors
- [ ] Markdown preview works
- [ ] PDF download works
- [ ] No console errors
- [ ] API endpoints respond correctly
- [ ] Responsive design works (mobile/tablet/desktop)
- [ ] CORS configured properly
- [ ] Error messages are user-friendly

---

## 📚 Useful Commands

### Frontend

```bash
# Development
npm run dev              # Start dev server
npm run build            # Build for production
npm run preview          # Preview production build
npm run lint             # Run linter

# Maintenance
npm install              # Install dependencies
npm update               # Update dependencies
npm audit fix            # Fix security issues
```

### Backend

```bash
# Development
python -m uvicorn api.index:app --reload        # Dev server
python -m uvicorn api.index:app --reload --log-level debug  # With debug logs

# Testing
python -m pytest         # Run tests (if you add them)

# Maintenance
pip install -r requirements.txt     # Install dependencies
pip freeze > requirements.txt       # Update requirements
pip list --outdated                 # Check for updates
```

---

## 🎯 Best Practices

### Code Style

**Frontend (JavaScript/React):**
- Use functional components
- Use hooks (useState, useEffect)
- Keep components small
- Add comments for complex logic

**Backend (Python):**
- Follow PEP 8 style guide
- Use type hints
- Add docstrings to functions
- Handle exceptions properly

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and commit
git add .
git commit -m "feat: add my feature"

# Push and create PR
git push origin feature/my-feature
```

### Commit Messages

Follow conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Formatting
- `refactor:` - Code refactoring
- `test:` - Tests
- `chore:` - Maintenance

---

## 🚀 Performance Tips

### Frontend
- Use React.memo for expensive components
- Debounce markdown preview updates
- Lazy load heavy components

### Backend
- Cache markdown parsing results
- Optimize PDF generation
- Use async/await properly
- Add rate limiting if needed

---

## 📖 Learning Resources

### React & Vite
- [React Docs](https://react.dev/)
- [Vite Guide](https://vitejs.dev/guide/)

### FastAPI & Python
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- [Python Official Docs](https://docs.python.org/)

### Markdown
- [Markdown Guide](https://www.markdownguide.org/)

---

## 🤝 Contributing

When contributing:

1. Read the code
2. Understand the architecture
3. Make small, focused changes
4. Test thoroughly
5. Update documentation
6. Create meaningful commits

---

## 💡 Tips & Tricks

### Quick Restart

Create a script `dev.sh` (Mac/Linux) or `dev.bat` (Windows):

**dev.bat (Windows):**
```batch
@echo off
start cmd /k "python -m uvicorn api.index:app --reload"
start cmd /k "npm run dev"
```

**dev.sh (Mac/Linux):**
```bash
#!/bin/bash
python -m uvicorn api.index:app --reload &
npm run dev
```

### Environment Variables

Create `.env.local`:
```
VITE_API_URL=http://localhost:8000
```

Use in React:
```javascript
const apiUrl = import.meta.env.VITE_API_URL;
```

---

Happy Coding! 🎉

For more information, see:
- `ARCHITECTURE.md` - System design
- `DEPLOYMENT.md` - Deployment guide
- `README.md` - Overview
