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

- **React** - UI framework
- **Vite** - Build tool and dev server
- **marked** - Markdown parser
- **jsPDF** - PDF generation
- **html2canvas** - HTML to canvas conversion
- **Vercel** - Hosting and deployment

## 🛠️ Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
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

## 🎨 Customization

### Styling

Edit `src/App.css` to customize colors, fonts, and layout.

### Markdown Parser

The app uses `marked` library. Configure options in `src/App.jsx`:

```javascript
import { marked } from 'marked'

// Configure marked options
marked.setOptions({
  breaks: true,
  gfm: true,
  // Add more options
})
```

### PDF Settings

Customize PDF output in the `convertToPdf` function in `src/App.jsx`:

```javascript
const pdf = new jsPDF({
  orientation: 'portrait', // or 'landscape'
  unit: 'mm',
  format: 'a4' // or 'letter', etc.
})
```

## 🤝 Contributing

Contributions are welcome! Feel free to submit issues and pull requests.

## 📄 License

MIT

## 🔗 Links

- [Live Demo](https://your-app.vercel.app) (Update after deployment)
- [Report Bug](https://github.com/yourusername/markdown-to-pdf/issues)
- [Request Feature](https://github.com/yourusername/markdown-to-pdf/issues)

---

Built with ❤️ using React + Vite
