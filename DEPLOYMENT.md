# 🚀 Deployment Guide for Vercel

This guide will help you deploy your Markdown to PDF Converter to Vercel.

## Prerequisites

- [Node.js](https://nodejs.org/) installed (v18 or higher)
- [Git](https://git-scm.com/) installed
- A [Vercel](https://vercel.com) account (free)
- A [GitHub](https://github.com) account (optional, but recommended)

## Method 1: Deploy via Vercel CLI (Fastest)

### Step 1: Install Vercel CLI

```bash
npm install -g vercel
```

### Step 2: Login to Vercel

```bash
vercel login
```

This will open a browser window to authenticate.

### Step 3: Deploy

Navigate to the project directory and run:

```bash
# For preview deployment
vercel

# For production deployment
vercel --prod
```

The CLI will guide you through:
- Setting up the project
- Choosing a project name
- Configuring build settings (auto-detected from vercel.json)

That's it! Your app will be deployed and you'll get a URL.

---

## Method 2: Deploy via GitHub + Vercel Dashboard (Recommended for Teams)

### Step 1: Initialize Git (if not already done)

```bash
git init
git add .
git commit -m "Initial commit: Markdown to PDF Converter"
```

### Step 2: Create a GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Create a new repository (e.g., `markdown-to-pdf`)
3. Don't initialize with README (we already have one)

### Step 3: Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/markdown-to-pdf.git
git branch -M main
git push -u origin main
```

### Step 4: Deploy on Vercel

1. Go to [vercel.com/dashboard](https://vercel.com/dashboard)
2. Click **"Add New..."** → **"Project"**
3. Click **"Import Git Repository"**
4. Select your GitHub repository
5. Vercel will auto-detect the Vite framework
6. Click **"Deploy"**

Vercel will:
- Auto-detect the framework (Vite)
- Use the build settings from `vercel.json`
- Build and deploy your app
- Provide you with a production URL (e.g., `https://your-project.vercel.app`)

### Step 5: Automatic Deployments

Now, every time you push to GitHub:
- Push to `main` branch → Production deployment
- Push to other branches → Preview deployment

---

## Method 3: Manual Deployment from Local Build

### Step 1: Build the project

```bash
npm run build
```

This creates a `dist` folder with the production build.

### Step 2: Deploy the dist folder

```bash
# Install Vercel CLI if not already
npm install -g vercel

# Login
vercel login

# Deploy the dist folder
vercel --prod dist
```

---

## Environment Variables (If Needed Later)

If you need to add environment variables:

### Via Vercel Dashboard:
1. Go to your project on Vercel
2. Settings → Environment Variables
3. Add your variables

### Via Vercel CLI:
```bash
vercel env add VARIABLE_NAME
```

### In Code:
Access them via `import.meta.env.VITE_VARIABLE_NAME`

---

## Custom Domain Setup

### Step 1: Add Domain in Vercel

1. Go to your project on Vercel
2. Settings → Domains
3. Add your custom domain

### Step 2: Configure DNS

Add these DNS records at your domain registrar:

**For root domain (example.com):**
```
Type: A
Name: @
Value: 76.76.21.21
```

**For www subdomain:**
```
Type: CNAME
Name: www
Value: cname.vercel-dns.com
```

### Step 3: Verify

Vercel will automatically verify and issue an SSL certificate.

---

## Troubleshooting

### Build fails on Vercel

Check that:
1. Node version is compatible (set in `package.json` if needed)
2. All dependencies are in `package.json`, not just `devDependencies`
3. Build command is correct: `npm run build`

### Large bundle size warning

This is normal for PDF generation apps. To optimize:

```javascript
// In vite.config.js
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'pdf-libs': ['jspdf', 'html2canvas'],
          'markdown': ['marked']
        }
      }
    }
  }
})
```

### App doesn't work after deployment

1. Check browser console for errors
2. Verify build completed successfully
3. Check that all assets are loading (check Network tab)

---

## Useful Commands

```bash
# View deployment logs
vercel logs <deployment-url>

# List all deployments
vercel ls

# Remove a deployment
vercel rm <deployment-url>

# Open project in Vercel dashboard
vercel --open

# Pull environment variables locally
vercel env pull
```

---

## Production Checklist

Before deploying to production:

- [ ] Test the app thoroughly locally
- [ ] Run `npm run build` successfully
- [ ] Update README.md with your live URL
- [ ] Remove any console.log statements
- [ ] Optimize images (if any)
- [ ] Test on multiple browsers
- [ ] Test responsive design
- [ ] Set up custom domain (optional)
- [ ] Configure analytics (optional)

---

## Post-Deployment

After successful deployment:

1. **Test the live site**: Visit your Vercel URL and test all features
2. **Update README**: Add your live URL to the README
3. **Share**: Share your deployed app!

Your app is now live at: `https://your-project-name.vercel.app`

---

## Continuous Deployment

With GitHub integration:

```bash
# Make changes
git add .
git commit -m "Add new feature"
git push

# Vercel automatically deploys!
```

---

## Support

- [Vercel Documentation](https://vercel.com/docs)
- [Vite Documentation](https://vitejs.dev/)
- [GitHub Issues](https://github.com/yourusername/markdown-to-pdf/issues)

Happy deploying! 🚀
