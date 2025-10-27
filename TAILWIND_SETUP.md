# Tailwind CSS & DaisyUI Local Compilation Setup

This project now uses locally compiled Tailwind CSS and DaisyUI instead of CDN versions for better performance and customization.

## Prerequisites

- Node.js (v14 or higher)
- npm (comes with Node.js)

## Installation

1. Install dependencies:
```bash
npm install
```

This will install:
- `tailwindcss` - Utility-first CSS framework
- `daisyui` - Component library for Tailwind

## Build Commands

### Production Build (Minified)
```bash
npm run build:css
```
This compiles `static/css/input.css` → `static/css/output.css` (minified)

### Development Mode (Watch)
```bash
npm run watch:css
```
or
```bash
npm run dev
```
This watches for changes in:
- `templates/**/*.html`
- `static/js/**/*.js`
- `static/css/input.css`

And automatically rebuilds `static/css/output.css` when changes are detected.

## File Structure

```
sketchmaker/
├── package.json              # Node dependencies and build scripts
├── tailwind.config.js        # Tailwind configuration
├── static/
│   └── css/
│       ├── input.css        # Source CSS with Tailwind directives
│       └── output.css       # Generated CSS (gitignored)
└── templates/               # HTML templates (scanned by Tailwind)
```

## Configuration

### tailwind.config.js
Contains:
- Content paths (which files to scan for classes)
- Dark mode configuration
- Theme extensions (fonts, colors, etc.)
- DaisyUI plugin and theme settings

### static/css/input.css
Contains:
- Tailwind directives (`@tailwind base`, `@tailwind components`, `@tailwind utilities`)
- Custom CSS organized in Tailwind layers
- All custom styles from the old inline `<style>` tags

## Development Workflow

1. **Start watch mode** (in a separate terminal):
```bash
npm run dev
```

2. **Start Flask development server**:
```bash
python app.py
```

3. Make changes to:
   - HTML templates → CSS rebuilds automatically
   - `static/css/input.css` → CSS rebuilds automatically
   - JavaScript files → CSS rebuilds automatically (if you use new Tailwind classes)

4. **Before deploying/committing**, run production build:
```bash
npm run build:css
```

## What Changed

### Before (CDN)
```html
<link href="https://cdn.jsdelivr.net/npm/daisyui@4.7.2/dist/full.min.css" rel="stylesheet" />
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = { ... }
</script>
<style>
  /* Hundreds of lines of custom CSS */
</style>
```

### After (Local Compilation)
```html
<link href="{{ url_for('static', filename='css/output.css') }}?v=20250127" rel="stylesheet" />
```

## Benefits

✅ **Faster Page Loads** - Single optimized CSS file instead of multiple CDN requests
✅ **Better Caching** - Versioned CSS with cache-busting parameter
✅ **Smaller File Size** - Purges unused CSS classes (only includes what you use)
✅ **No External Dependencies** - Works offline, no CDN downtime
✅ **Better Customization** - Full control over Tailwind config and custom CSS
✅ **Production Ready** - Minified and optimized for production

## Troubleshooting

### CSS not updating?
1. Make sure watch mode is running: `npm run dev`
2. Check if `static/css/output.css` was generated
3. Hard refresh browser: `Ctrl + F5`

### Build errors?
```bash
# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Rebuild
npm run build:css
```

### Styles missing?
1. Check that HTML files are in `templates/**/*.html` (covered by Tailwind config)
2. Verify classes are not dynamically generated (Tailwind needs to see the full class name)
3. Check browser console for CSS loading errors

## Cache Busting

The CSS link includes a version parameter:
```html
<link href="...?v=20250127" />
```

When deploying updates, change this version number in `templates/base.html` to force browsers to download the new CSS.
