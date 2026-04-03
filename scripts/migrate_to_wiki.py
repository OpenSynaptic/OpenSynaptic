#!/usr/bin/env python3
"""
Migrate documentation from docs/ to OpenSynaptic.wiki/ with GitHub Wiki naming convention.

GitHub Wiki naming: subdirectory paths are converted to hyphens (e.g., guides/api.md -> guides-api)
Links are updated from relative paths to wiki-format links.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Tuple, Set

# Configuration
DOCS_BASE = Path("docs")
WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")
LANGUAGES = ["en", "zh"]

# Track all files and their mappings for link conversion
FILE_MAPPINGS: Dict[str, Dict[str, str]] = {}  # {lang: {original_path: wiki_name}}


def wiki_filename(relative_path: str) -> str:
    """
    Convert a relative file path to GitHub Wiki naming convention.
    Example: "guides/api.md" -> "guides-api"
    Example: "architecture/ARCH.md" -> "architecture-ARCH"
    """
    # Remove .md extension and replace / with -
    name = relative_path.replace(".md", "").replace("/", "-")
    return name


def convert_markdown_links(content: str, lang: str) -> str:
    """
    Convert markdown links from relative paths to wiki format.
    Examples:
    - [text](api.md) -> [text](api)
    - [text](guides/api.md) -> [text](guides-api)
    - [text](../en/api.md) -> [text](api) or [text](en-api) depending on cross-language
    """
    
    # Pattern for markdown links: [text](path)
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    def replace_link(match):
        text = match.group(1)
        path = match.group(2)
        
        # Skip external links and anchors
        if path.startswith("http://") or path.startswith("https://") or path.startswith("#"):
            return match.group(0)
        
        # Normalize path: remove ../ and ./
        original_path = path
        
        # Handle cross-language references like ../zh/file.md or ../en/file.md
        if "../zh/" in path:
            path = path.replace("../zh/", "")
            target_lang = "zh"
        elif "../en/" in path:
            path = path.replace("../en/", "")
            target_lang = "en"
        elif "../" in path:
            # Remove parent directory references
            while "../" in path:
                path = path.split("../")[-1]
            target_lang = lang
        else:
            target_lang = lang
        
        # Remove leading ./
        path = path.lstrip("./")
        
        # Skip if path is empty or just anchor
        if not path or path.startswith("#"):
            return match.group(0)
        
        # Convert to wiki format
        wiki_name = wiki_filename(path)
        
        # Add language prefix if referencing different language
        if target_lang != lang:
            wiki_name = f"{target_lang}-{wiki_name}"
        
        return f"[{text}]({wiki_name})"
    
    return re.sub(link_pattern, replace_link, content)


def migrate_file(src_path: Path, lang: str) -> bool:
    """
    Migrate a single file from docs/{lang}/ to wiki with proper naming and link conversion.
    Returns True if successful.
    """
    try:
        # Get relative path from lang directory
        relative_path = src_path.relative_to(DOCS_BASE / lang)
        
        # Create wiki filename
        wiki_name = wiki_filename(str(relative_path))
        
        # Add language prefix
        wiki_filename_full = f"{lang}-{wiki_name}"
        wiki_path = WIKI_BASE / f"{wiki_filename_full}.md"
        
        # Track the mapping
        if lang not in FILE_MAPPINGS:
            FILE_MAPPINGS[lang] = {}
        FILE_MAPPINGS[lang][str(relative_path)] = wiki_name
        
        # Read source file
        with open(src_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Convert links
        converted_content = convert_markdown_links(content, lang)
        
        # Ensure wiki directory exists
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to wiki
        with open(wiki_path, 'w', encoding='utf-8') as f:
            f.write(converted_content)
        
        print(f"✓ Migrated: {relative_path} -> {wiki_filename_full}.md")
        return True
    
    except Exception as e:
        print(f"✗ Error migrating {src_path}: {e}")
        return False


def scan_and_migrate():
    """Scan all docs and migrate to wiki."""
    total = 0
    success = 0
    
    for lang in LANGUAGES:
        lang_path = DOCS_BASE / lang
        if not lang_path.exists():
            print(f"⚠ Language directory not found: {lang_path}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Migrating {lang.upper()} documentation")
        print(f"{'='*60}")
        
        # Walk through all .md files
        for md_file in lang_path.rglob("*.md"):
            total += 1
            if migrate_file(md_file, lang):
                success += 1
    
    print(f"\n{'='*60}")
    print(f"Migration Summary")
    print(f"{'='*60}")
    print(f"Total files: {total}")
    print(f"Successfully migrated: {success}")
    print(f"Failed: {total - success}")
    
    return success == total


def update_wiki_navigation():
    """
    Create/update the _Sidebar.md to include links to migrated docs.
    """
    sidebar_path = WIKI_BASE / "_Sidebar.md"
    
    sidebar_content = """# OpenSynaptic Wiki Navigation

## English Documentation
- [Home](Home)
- [README](en-README)
- [Architecture](en-ARCHITECTURE)
- [API Overview](en-API)
- [Configuration](en-CONFIG_SCHEMA)
- [Core API](en-CORE_API)

### Architecture
- [Core Pipeline](en-architecture-CORE_PIPELINE_INTERFACE_EXPOSURE)
- [Evolution Comparison](en-architecture-ARCHITECTURE_EVOLUTION_COMPARISON)
- [FFI Analysis](en-architecture-ARCHITECTURE_FFI_ANALYSIS)

### Plugins
- [Plugin Development Spec](en-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026)
- [Plugin Starter Kit](en-plugins-PLUGIN_STARTER_KIT)
- [Plugin Quick Reference](en-plugins-PLUGIN_QUICK_REFERENCE)

### Guides
- [Display API Guide](en-guides-DISPLAY_API_GUIDE)
- [Quick Reference](en-guides-QUICK_REFERENCE)

## 中文文档
- [主页](Home)
- [README](zh-README)
- [架构](zh-ARCHITECTURE)
- [API 概览](zh-API)
- [配置](zh-CONFIG_SCHEMA)

### 插件开发
- [插件开发规范](zh-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026)
- [插件快速入门](zh-plugins-PLUGIN_STARTER_KIT)

### 指南
- [快速参考](zh-guides-QUICK_REFERENCE)
"""
    
    try:
        with open(sidebar_path, 'w', encoding='utf-8') as f:
            f.write(sidebar_content)
        print(f"✓ Updated {sidebar_path}")
    except Exception as e:
        print(f"✗ Failed to update sidebar: {e}")


def main():
    """Main migration entry point."""
    print("OpenSynaptic Documentation Migration to Wiki")
    print("=" * 60)
    print(f"Source: {DOCS_BASE}")
    print(f"Target: {WIKI_BASE}")
    print(f"Languages: {', '.join(LANGUAGES)}")
    print()
    
    # Check if wiki base exists
    if not WIKI_BASE.exists():
        print(f"⚠ Wiki base directory not found: {WIKI_BASE}")
        print("Creating it now...")
        WIKI_BASE.mkdir(parents=True, exist_ok=True)
    
    # Perform migration
    if scan_and_migrate():
        print("\n✓ All files migrated successfully!")
        
        # Update navigation
        print("\nUpdating wiki navigation...")
        update_wiki_navigation()
        
        print("\n" + "=" * 60)
        print("Next steps:")
        print("1. Review migrated files in: " + str(WIKI_BASE))
        print("2. Update Home.md to reference new pages")
        print("3. Commit changes to git")
        print("=" * 60)
    else:
        print("\n⚠ Some files failed to migrate. Check errors above.")


if __name__ == "__main__":
    main()
