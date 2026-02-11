# 📄 Markdown to PDF Converter

A beautiful, modern web application to convert Markdown to PDF with real-time preview. Built with React, Vite, and deployed on Vercel.

## ✨ Features

- 📝 Real-time Markdown editor with syntax highlighting
- 👁️ Live HTML preview
- 📥 One-click PDF export
- 🎨 Beautiful, modern UI with gradient design
- 📱 Fully responsive design
- ⚡ Fast and lightweight

## 🚀 Tech Stack

### Frontend
- **React 19.2** - Modern UI framework
- **Vite 7.3** - Lightning-fast build tool
- **marked** - Markdown preview

### Backend
- **FastAPI 0.115** - Modern Python web framework
- **Python 3.9+** - Backend language
- **markdown** - Markdown parser
- **xhtml2pdf** - PDF generation engine
- **reportlab** - PDF library

### Deployment
- **Vercel** - Full-stack hosting (frontend + serverless functions)

## 🛠️ Installation

### Prerequisites
- Node.js 18+ and npm
- Python 3.9+ and pip

### Install Dependencies

```bash
# Frontend dependencies
npm install

# Backend dependencies
pip install -r requirements.txt
```

### Development

You need TWO terminal windows:

**Terminal 1 - Backend:**
```bash
python -m uvicorn api.index:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

Then open: **http://localhost:5173**

### Production Build

```bash
# Build frontend
npm run build

# Preview
npm run preview
```

## 📦 Deployment to Vercel

### Option 1: Using Vercel CLI

```bash
# Install Vercel CLI globally
npm install -g vercel

# Login to Vercel
vercel login

# Deploy
vercel

# Deploy to production
vercel --prod
```

### Option 2: Using Vercel Dashboard

1. Push your code to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Click "New Project"
4. Import your GitHub repository
5. Vercel will auto-detect the Vite framework
6. Click "Deploy"

### Option 3: Using Git Integration

```bash
# Connect to Vercel (first time only)
vercel

# Subsequent deployments - just push to git
git add .
git commit -m "Update"
git push
```

## 🎯 Usage

1. **Write Markdown**: Type or paste your markdown content in the left editor panel
2. **Preview**: See the rendered HTML in the right preview panel in real-time
3. **Export**: Click the "Download PDF" button to generate and download your PDF

## 📝 Supported Markdown Features

- Headers (H1-H6)
- Bold and italic text
- Lists (ordered and unordered)
- Code blocks and inline code
- Blockquotes
- Links
- Images
- Tables
- Horizontal rules
- And more!

## 🏗️ Architecture

This is a **full-stack application** with clear separation:

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   React     │      │   FastAPI   │      │     PDF     │
│   + Vite    │ ───► │  + Python   │ ───► │   Output    │
│  (UI Only)  │ HTTP │ (Business)  │      │  (File)     │
└─────────────┘      └─────────────┘      └─────────────┘
```

- **Frontend**: Handles UI, editing, and preview
- **Backend**: Handles markdown parsing and PDF generation
- **API**: RESTful communication between frontend and backend

For detailed architecture, see `ARCHITECTURE.md`

## 🎨 Customization

### Frontend Styling

Edit `src/App.css` to customize colors, fonts, and layout:

```css
.app {
  background: linear-gradient(135deg, #your-color 0%, #another-color 100%);
}
```

### PDF Styling

Edit `api/index.py` → `HTML_TEMPLATE` to customize PDF output:

```python
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Your Font', sans-serif; }
        h1 { color: #your-color; }
    </style>
</head>
<body>{content}</body>
</html>
"""
```

### PDF Settings

Modify PDF generation in `api/index.py` for different page sizes, margins, etc.

## 🤝 Contributing

Contributions are welcome! Feel free to submit issues and pull requests.

## 📄 License

MIT

## 📚 Documentation

- **ARCHITECTURE.md** - System design and data flow
- **DEVELOPMENT.md** - Development guide and best practices
- **DEPLOYMENT.md** - Deployment instructions
- **QUICKSTART.md** - Quick start guide

## 🧪 API Documentation

When running locally, FastAPI provides interactive API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🔗 Links

- [Live Demo](https://your-app.vercel.app) (Update after deployment)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [React Docs](https://react.dev/)
- [Vite Docs](https://vitejs.dev/)

---

Built with ❤️ using React + Vite + FastAPI + Python
