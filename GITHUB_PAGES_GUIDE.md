# GitHub Pages Multi-Language Deployment Guide

## Quick Start

OpenSynaptic documentation now supports **multiple languages** on GitHub Pages.

### Current Language Support

- **English** - Original documentation at `/docs/`
- **简体中文 (Chinese)** - Chinese translations at `/docs/zh/`

---

## For Users

### Accessing Documentation

1. **Visit Language Selector**: Open [Wiki Home](https://github.com/OpenSynaptic/OpenSynaptic/wiki/Home) in browser
2. **Switch Languages**: Click language cards to navigate
3. **Direct URLs**:
   - English: `https://opensynaptic.github.io/`
   - Chinese: `https://opensynaptic.github.io/zh/`

### Language Switcher in Every Page

Each documentation page has language toggle links in the header:
- Shows current language
- Provides link to switch to other language
- Maintains page context (tries to show same page in different language)

---

## For Contributors

### Adding New Documentation

1. **Create English version** in `docs/` directory
   ```yaml
   ---
   layout: default
   title: Page Title
   language: en
   ---
   # Page content...
   ```

2. **Create Chinese translation** in `docs/zh/` directory
   ```yaml
   ---
   layout: default
   title: 页面标题
   language: zh
   ---
   # 页面内容...
   ```

3. **Add language links**:
   ```markdown
   **Language**: [English](../FILENAME.md) | [中文](FILENAME.md)
   ```

### File Structure

```
docs/
├── index.html                    # Language selector (entry point)
├── _config.yml                   # Jekyll configuration
├── _layouts/default.html         # Base layout with language switcher
├── assets/css/style.css          # Shared styles
├── README.md | INDEX.md | *.md   # English documentation
└── zh/
    ├── README.md | INDEX.md      # Chinese documentation
    └── *.md
```

### Testing Locally

```bash
# Install dependencies
cd docs
bundle install  # First time only

# Build site
bundle exec jekyll build

# Serve locally
bundle exec jekyll serve

# Visit http://localhost:4000
```

### Deploying

Push changes to `main` or `master` branch:
```bash
git add docs/
git commit -m "docs: add Chinese translation for XYZ"
git push origin main
```

GitHub Actions will automatically:
1. Build Jekyll site
2. Validate markdown
3. Deploy to GitHub Pages (if on main branch)

---

## Technical Details

### Jekyll Configuration

`docs/_config.yml` defines:
- Language list with codes
- Theme and plugins
- Build settings

```yaml
languages:
  en:
    name: "English"
    code: "en"
  zh:
    name: "简体中文"
    code: "zh"
    path: "/zh/"
```

### Layout System

`docs/_layouts/default.html` provides:
- Automatic language switcher
- Context-aware navigation
- Consistent styling across languages

Template variables available:
- `site.languages` - All configured languages
- `page.language` - Current page language
- `site.default_language` - Fallback language

### Styling

`docs/assets/css/style.css` includes:
- Language switcher styling
- Multi-language responsive design
- Dark mode support

---

## Common Tasks

### Update Existing Page

1. Edit English version: `docs/FILENAME.md`
2. Sync Chinese version: `docs/zh/FILENAME.md`
3. Push changes

### Add New Language

1. Update `docs/_config.yml`: Add language to `languages` section
2. Create language directory: `mkdir docs/[lang-code]/`
3. Update `docs/index.html`: Add language card
4. Update `docs/_layouts/default.html`: Add to language switcher
5. Start translating docs

### Fix Broken Link

1. Identify broken file path
2. For English: Fix in `docs/*.md`
3. For Chinese: Fix in `docs/zh/*.md`
4. Wait for auto-deploy or test locally first

---

## Troubleshooting

### Links Return 404

**Cause**: Incorrect relative paths  
**Fix**: 
- Use `[text](file.md)` in `/zh/` files (same directory)
- Use `[text](../en/file.md)` for cross-language links

### Chinese Not Displaying

**Cause**: Encoding issue  
**Fix**: 
- Ensure file saved as UTF-8
- Check markdown front matter is valid YAML

### Pages Not Updating

**Cause**: Build failure or cache  
**Fix**:
- Check GitHub Actions workflow status
- Clear browser cache
- Wait 5 minutes for deployment

### Local Build Fails

**Cause**: Missing dependencies  
**Fix**:
```bash
cd docs
bundle install --path vendor/bundle
bundle exec jekyll build
```

---

## Reference

- **Multi-Language Guide**: [docs/MULTI_LANGUAGE_GUIDE.md](https://github.com/OpenSynaptic/OpenSynaptic/wiki/en-MULTI_LANGUAGE_GUIDE)
- **Jekyll Docs**: https://jekyllrb.com/
- **GitHub Pages**: https://pages.github.com/
- **Markdown Guide**: https://www.markdownguide.org/

---

## Questions?

1. Check [MULTI_LANGUAGE_GUIDE.md](https://github.com/OpenSynaptic/OpenSynaptic/wiki/en-MULTI_LANGUAGE_GUIDE) for detailed info
2. Review example files in `docs/zh/`
3. Open an issue on GitHub
4. Check GitHub Actions logs for deployment errors

---

**Status**: ✅ Multi-language support live on GitHub Pages  
**Last Updated**: 2026-04-04
