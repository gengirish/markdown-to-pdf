# 🚀 Quick Start Guide

Get your Markdown to PDF Converter up and running in minutes!

## Local Development

### 1. Start the Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### 2. Make Changes

Edit files in `src/` and see live updates with Hot Module Replacement (HMR).

### 3. Test the Build

```bash
npm run build
npm run preview
```

---

## Deploy to Vercel (Fastest Method)

### Option A: One-Command Deploy

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy (first time - will ask setup questions)
vercel

# Or deploy directly to production
vercel --prod
```

### Option B: GitHub + Vercel (Recommended)

```bash
# 1. Create a new repo on GitHub
# 2. Push your code
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git push -u origin master

# 3. Go to vercel.com
# 4. Click "New Project"
# 5. Import from GitHub
# 6. Click "Deploy"
```

Done! Your app is live! 🎉

---

## Project Structure

```
tool/
├── src/
│   ├── App.jsx          # Main application component
│   ├── App.css          # Application styles
│   ├── main.jsx         # React entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── dist/                # Production build (generated)
├── vercel.json          # Vercel configuration
├── DEPLOYMENT.md        # Detailed deployment guide
└── package.json         # Dependencies
```

---

## Common Tasks

### Update Dependencies

```bash
npm update
```

### Add a New Feature

```bash
# 1. Create a new branch
git checkout -b feature-name

# 2. Make changes
# 3. Test locally
npm run dev

# 4. Commit and push
git add .
git commit -m "Add feature-name"
git push

# Vercel will automatically create a preview deployment!
```

### Customize Styles

Edit `src/App.css` to change colors, fonts, layout, etc.

### Change PDF Settings

Edit the `convertToPdf` function in `src/App.jsx`:

```javascript
const pdf = new jsPDF({
  orientation: 'portrait',  // or 'landscape'
  unit: 'mm',
  format: 'a4'             // or 'letter', 'legal', etc.
})
```

---

## Troubleshooting

### Port already in use

```bash
# Kill the process using port 5173
npx kill-port 5173

# Or use a different port
npm run dev -- --port 3000
```

### Build fails

```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
npm run build
```

### PDF not generating

Check browser console for errors. Most common issues:
- Content too large (try smaller text)
- Special characters (try simpler markdown)
- Browser compatibility (use Chrome/Edge)

---

## Need Help?

- Read `DEPLOYMENT.md` for detailed deployment instructions
- Read `README.md` for full documentation
- Check the [Vite docs](https://vitejs.dev/)
- Check the [Vercel docs](https://vercel.com/docs)

---

Happy coding! 💻✨
