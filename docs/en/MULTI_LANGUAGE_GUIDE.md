---
layout: default
title: Multi-Language Documentation Guide
language: en
---

# Multi-Language Documentation Guide

**Language**: [English](MULTI_LANGUAGE_GUIDE.md) | [简体中文](zh/MULTI_LANGUAGE_GUIDE.md)  
**Last updated**: 2026-04-04

This guide explains how the OpenSynaptic documentation supports multiple languages on GitHub Pages.

---

## Overview

The OpenSynaptic project provides documentation in multiple languages:

- **English** (`/en/` or root `/`) - Original documentation
- **简体中文 (Simplified Chinese)** (`/zh/`) - Chinese translations

### Directory Structure

```
docs/
├── index.html              # Language selector page
├── _config.yml             # Jekyll configuration
├── _layouts/
│   └── default.html        # Base layout with language switcher
├── assets/
│   └── css/style.css       # Shared styles
├── README.md               # English documentation hub
├── INDEX.md                # English documentation index
├── ARCHITECTURE.md         # English architecture docs
├── API.md                  # English API reference
├── [other-docs].md         # Other English documentation
│
└── zh/                     # Chinese translations
    ├── README.md           # 中文文档中心
    ├── INDEX.md            # 中文文档索引
    ├── ARCHITECTURE.md     # 中文架构文档
    ├── MULTI_LANGUAGE_GUIDE.md  # 本指南的中文版
    └── [other-docs].md     # Other Chinese documentation
```

---

## Language Switching

### For Users

Users can switch languages in three ways:

1. **Language Selector Page**: Visit [index.html](index.html) to choose language
2. **Header Links**: Each page has language toggle links in the header
3. **Direct URL Navigation**: 
   - English: `/docs/FILENAME.md` or `/docs/en/FILENAME.md`
   - Chinese: `/docs/zh/FILENAME.md`

### How It Works

The Jekyll `_config.yml` defines language settings:

```yaml
languages:
  en:
    name: "English"
    code: "en"
    path: "/en/"
  zh:
    name: "简体中文"
    code: "zh"
    path: "/zh/"
```

Front matter in each markdown file specifies the language:

```yaml
---
layout: default
title: Page Title
language: en
---
```

The `_layouts/default.html` template uses this metadata to:
- Show current language in header
- Provide links to switch languages
- Customize navigation based on language context

---

## Adding Translations

### Step 1: Create Chinese Directory Structure

Create corresponding files in the `docs/zh/` directory:

```bash
docs/zh/
├── README.md           # Translated from docs/README.md
├── INDEX.md            # Translated from docs/INDEX.md
├── ARCHITECTURE.md     # Translated from docs/ARCHITECTURE.md
└── ...
```

### Step 2: Add YAML Front Matter

Every markdown file must start with language specification:

```yaml
---
layout: default
title: [Page Title in Current Language]
language: zh
---

# Page Content
```

### Step 3: Translate Content

- Translate the page title and all content
- Maintain the same markdown structure as original
- Update all internal link paths:
  - Change `[link](../README.md)` to `[link](README.md)` in `/zh/` files (same directory)
  - Use relative paths correctly for cross-language links

### Step 4: Add Language Toggle Links

At the top/bottom of translated pages, add:

```markdown
**Language**: [English](../FILENAME.md) | [中文](FILENAME.md)
```

Or in the front matter:

```yaml
---
layout: default
title: Page Title
language: zh
---
```

The template will automatically handle language switching.

### Step 5: Update Navigation

If adding new sections:

1. Update both English and Chinese INDEX.md files
2. Add language toggle links
3. Update any affected navigation pages

---

## Translation Guidelines

### Tone and Style

- **Maintain consistency**: Use the same terminology throughout translations
- **Be accurate**: Translate technical terms correctly (e.g., "Fusion Engine" → "融合引擎")
- **Natural flow**: Adapt sentences for Chinese grammar (not word-for-word)
- **Audience**: Assume technical readers familiar with IoT and Python

### Technical Terminology

Keep a consistent glossary for technical terms:

| English | Chinese | Context |
|---------|---------|---------|
| Fusion Engine | 融合引擎 | Core component |
| Pipeline | 管道 | Data processing flow |
| Transporter | 传输器 / 传输驱动程序 | Plugin system |
| Base62 Compression | Base62 压缩 | Data encoding |
| ID Lease System | ID 租赁系统 | Device management |
| Backend | 后端 | Pycore/Rscore choice |
| Standardization | 标准化 | UCUM unit conversion |

### Code Examples

Keep code unchanged, but translate comments and surrounding text:

```python
# English
def compress(data: bytes) -> str:
    """Convert binary data to Base62 format."""
    return base62_encode(data)

# Chinese (Comments translated, code identical)
def compress(data: bytes) -> str:
    """将二进制数据转换为 Base62 格式。"""
    return base62_encode(data)
```

---

## Deployment

### GitHub Pages Workflow

The `.github/workflows/pages.yml` automatically:

1. **Triggers on**: Push to main/master, changes to `docs/` folder
2. **Builds**: Runs Jekyll to generate HTML from markdown
3. **Deploys**: Uploads to GitHub Pages if on main branch
4. **Validates**: Checks markdown syntax and link structure on PRs

### Manual Deployment

To test locally before pushing:

```bash
# Install Jekyll
gem install jekyll bundler

# Navigate to docs directory
cd docs

# Install dependencies
bundle install

# Build site
bundle exec jekyll build

# View locally (optional)
bundle exec jekyll serve
# Visit http://localhost:4000
```

---

## Language-Specific Features

### Front Matter Variables

In any markdown file, you can use:

```yaml
---
layout: default
title: Page Title
language: en
toc: true              # Enable table of contents
description: Brief description
---
```

### Conditional Content

Use Jekyll Liquid templating in your markdown:

```liquid
{% if page.language == 'zh' %}
  [Content for Chinese]
{% else %}
  [Content for English]
{% endif %}
```

### Language-Specific Navigation

The default layout automatically generates:
- Language toggle links in header
- Appropriate navigation menu for current language
- GitHub link in footer

---

## Best Practices

### Do's ✅

- ✅ Keep English and Chinese documentation in sync
- ✅ Use consistent front matter structure
- ✅ Test links before submitting PR
- ✅ Use relative paths for internal links
- ✅ Add language toggle at top/bottom of pages
- ✅ Update both language versions when fixing docs
- ✅ Use semantic HTML in layout files

### Don'ts ❌

- ❌ Don't hardcode absolute paths
- ❌ Don't mix English and Chinese in same file (except code)
- ❌ Don't skip YAML front matter
- ❌ Don't forget language links in new pages
- ❌ Don't edit deployed site directly
- ❌ Don't rely on automatic translation tools (quality may vary)
- ❌ Don't change directory structure without updating config

---

## Contributing Translations

To contribute translations:

1. **Fork the repository**
2. **Create a branch**: `git checkout -b docs/add-zh-translation`
3. **Add/update translation files** in `docs/zh/`
4. **Follow guidelines above**
5. **Test locally** using Jekyll (see Deployment section)
6. **Submit PR** with description of translated pages

### PR Checklist

- [ ] All YAML front matter is correct
- [ ] Language links are bidirectional
- [ ] Relative paths are correct
- [ ] No HTML/markdown syntax errors
- [ ] Terminology is consistent
- [ ] Links point to existing files
- [ ] Code examples are unchanged (only comments translated)
- [ ] No hardcoded absolute paths

---

## Adding New Languages

To add support for a new language (e.g., Spanish):

### 1. Update `docs/_config.yml`:

```yaml
languages:
  en:
    name: "English"
    code: "en"
  zh:
    name: "简体中文"
    code: "zh"
  es:
    name: "Español"
    code: "es"
    path: "/es/"
```

### 2. Create directory and files:

```bash
mkdir -p docs/es
cp docs/README.md docs/es/README.md
```

### 3. Update `docs/index.html`:

Add new language card in HTML language selector.

### 4. Update layout:

Edit `docs/_layouts/default.html` to include new language in switcher.

### 5. Start translating:

Add YAML front matter and translate content for each file.

---

## Troubleshooting

### Links Not Working

**Problem**: Links return 404 after publish  
**Solution**: 
- Check relative paths are correct
- Verify file exists in both English and translated versions
- Use `[text](filename.md)` not `[text](filename)` or `[text](filename.html)`

### Language Switcher Not Appearing

**Problem**: Header shows no language options  
**Solution**:
- Add YAML front matter with `language: en` or `language: zh`
- Check `_layouts/default.html` is properly updated
- Verify Jekyll build succeeds locally

### Chinese Characters Not Displaying

**Problem**: Chinese text shows as ???  
**Solution**:
- Ensure file is saved as UTF-8
- Check `<meta charset="utf-8">` in layout
- Verify _config.yml doesn't override encoding

### Build Fails in GitHub Actions

**Problem**: GitHub Pages deployment fails  
**Solution**:
- Check `.github/workflows/pages.yml` is present
- Verify `docs/_config.yml` exists and is valid YAML
- Ensure Gemfile is in docs directory
- Check workflow permissions in repository settings

---

## Resources

- [Jekyll Documentation](https://jekyllrb.com/)
- [GitHub Pages Guide](https://docs.github.com/en/pages)
- [Markdown Guide](https://www.markdownguide.org/)
- [OpenSynaptic Main Documentation](README.md)

---

## Support and Feedback

If you find translation issues or have suggestions:

1. Open an Issue on GitHub
2. Provide specific page and language
3. Suggest corrected translation if applicable
4. Reference this guide if relevant

---

**Last updated**: 2026-04-04  
**Maintained by**: OpenSynaptic Community  
**Language**: [English](MULTI_LANGUAGE_GUIDE.md) | [简体中文](zh/MULTI_LANGUAGE_GUIDE.md)
