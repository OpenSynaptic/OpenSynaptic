#!/usr/bin/env python3
"""
Generate navigation files for the GitHub Wiki.
"""

import os
from pathlib import Path
from collections import defaultdict

WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")

def parse_wiki_files():
    """Parse all wiki files and organize by language and category."""
    files_by_lang = defaultdict(lambda: defaultdict(list))
    
    # Walk through all markdown files
    for md_file in WIKI_BASE.glob("*.md"):
        filename = md_file.stem
        
        # Skip special files
        if filename.startswith("_") or filename == "Home":
            continue
        
        # Parse filename: either "en-FILENAME" or "zh-FILENAME"
        if filename.startswith("en-"):
            lang = "en"
            parts = filename[3:].split("-")
        elif filename.startswith("zh-"):
            lang = "zh"
            parts = filename[3:].split("-")
        else:
            continue
        
        # Determine category (first part of remaining name)
        if len(parts) > 1 and parts[0].lower() in ["api", "architecture", "features", "guides", 
                                                      "internal", "plugins", "releases", "reports"]:
            category = parts[0]
        else:
            category = "ROOT"
        
        files_by_lang[lang][category].append(filename)
    
    return files_by_lang


def generate_sidebar(files_data):
    """Generate _Sidebar.md content."""
    
    content = """# OpenSynaptic Wiki

## Navigation

### Getting Started
- [Home](Home)
- [English](en-README)
- [中文](zh-README)

---

## English Documentation

### Core References
- [Architecture](en-ARCHITECTURE)
- [API Overview](en-API)
- [Core API](en-CORE_API)
- [Configuration](en-CONFIG_SCHEMA)
- [Quick Start](en-QUICK_START)

### Architecture & Design
- [Core Pipeline Interface](en-architecture-CORE_PIPELINE_INTERFACE_EXPOSURE)
- [Architecture Evolution](en-architecture-ARCHITECTURE_EVOLUTION_COMPARISON)
- [FFI Analysis](en-architecture-ARCHITECTURE_FFI_ANALYSIS)
- [FFI Verification](en-architecture-FFI_VERIFICATION_DIAGRAMS)

### APIs & Protocols
- [Pycore/Rust API](en-PYCORE_RUST_API)
- [Rscore API](en-RSCORE_API)
- [Transporter Plugin](en-TRANSPORTER_PLUGIN)
- [Display API](en-guides-DISPLAY_API_GUIDE)
- [Display API Quickstart](en-guides-DISPLAY_API_QUICKSTART)

### Features
- [ID Lease System](en-ID_LEASE_SYSTEM)
- [ID Lease Config Reference](en-ID_LEASE_CONFIG_REFERENCE)

### Plugin Development
- [Plugin Development Spec](en-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026)
- [Plugin Starter Kit](en-plugins-PLUGIN_STARTER_KIT)
- [Plugin Quick Reference](en-plugins-PLUGIN_QUICK_REFERENCE)

### Guides
- [WEB Commands Reference](en-guides-WEB_COMMANDS_REFERENCE)
- [TUI Quick Reference](en-guides-TUI_QUICK_REFERENCE)
- [Restart Command Guide](en-guides-RESTART_COMMAND_GUIDE)
- [Quick Reference](en-guides-QUICK_REFERENCE)

### Release Information
- [Release Checklist](en-releases-RELEASE_CHECKLIST)
- [v1.1.0](en-releases-v1.1.0)
- [v0.3.0 Announcement](en-releases-v0.3.0_announcement)

### Additional Resources
- [Index](en-INDEX)
- [Internationalization Guide](en-I18N)
- [Documentation Organization](en-DOCUMENT_ORGANIZATION)

---

## 中文文档

### 核心参考
- [架构](zh-ARCHITECTURE)
- [API 概览](zh-API)
- [核心 API](zh-CORE_API)
- [配置](zh-CONFIG_SCHEMA)
- [快速开始](zh-QUICK_START)

### 插件开发
- [插件开发规范](zh-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026)
- [插件启动工具包](zh-plugins-PLUGIN_STARTER_KIT)
- [插件快速参考](zh-plugins-PLUGIN_QUICK_REFERENCE)

### 指南
- [快速参考](zh-guides-QUICK_REFERENCE)
- [重启命令指南](zh-guides-RESTART_COMMAND_GUIDE)

### 其他资源
- [索引](zh-INDEX)
- [文档组织](zh-DOCUMENT_ORGANIZATION)
- [国际化指南](zh-I18N)

---

### For More
- See [Full Index (en)](en-INDEX) or [Full Index (zh)](zh-INDEX) for complete documentation
"""
    
    return content


def generate_home():
    """Generate Home.md content."""
    
    content = """# Welcome to OpenSynaptic Wiki

OpenSynaptic is a 2-N-2 IoT protocol stack for standardizing, compressing, and efficiently dispatching sensor data.

## Quick Navigation

- **[English Documentation](en-README)** | **[中文文档](zh-README)**

### Start Here
1. [README](en-README) - Project overview and getting started
2. [Architecture](en-ARCHITECTURE) - System design and pipeline
3. [API Overview](en-API) - Core interfaces and APIs
4. [Configuration Reference](en-CONFIG_SCHEMA) - Configuration options

### For Plugin Developers
- [Plugin Development Specification](en-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026)
- [Plugin Starter Kit](en-plugins-PLUGIN_STARTER_KIT)
- [Plugin Quick Reference](en-plugins-PLUGIN_QUICK_REFERENCE)

### For Operators
- [Quick Start](en-QUICK_START)
- [Configuration Guide](en-ID_LEASE_CONFIG_REFERENCE)
- [WEB Commands Reference](en-guides-WEB_COMMANDS_REFERENCE)
- [TUI Quick Reference](en-guides-TUI_QUICK_REFERENCE)

### Browse All Documentation
- [Full English Index](en-INDEX)
- [Full Chinese Index](zh-INDEX)

---

Last updated: 2026-04-04
"""
    
    return content


def main():
    """Generate all navigation files."""
    
    print("Generating Wiki navigation files...")
    
    # Parse files
    files_data = parse_wiki_files()
    
    # Generate and write _Sidebar.md
    sidebar_content = generate_sidebar(files_data)
    sidebar_path = WIKI_BASE / "_Sidebar.md"
    with open(sidebar_path, 'w', encoding='utf-8') as f:
        f.write(sidebar_content)
    print(f"✓ Created {sidebar_path}")
    
    # Generate and write Home.md
    home_content = generate_home()
    home_path = WIKI_BASE / "Home.md"
    with open(home_path, 'w', encoding='utf-8') as f:
        f.write(home_content)
    print(f"✓ Created {home_path}")
    
    # Also generate a _Footer.md
    footer_content = """---

**OpenSynaptic Project** | [GitHub](https://github.com/opensynaptic/opensynaptic) | Updated: 2026-04-04
"""
    footer_path = WIKI_BASE / "_Footer.md"
    with open(footer_path, 'w', encoding='utf-8') as f:
        f.write(footer_content)
    print(f"✓ Created {footer_path}")
    
    print("\n✓ Wiki navigation setup complete!")
    print(f"\nWiki location: {WIKI_BASE}")
    print("\nNext steps:")
    print("1. Review the generated navigation files")
    print("2. Commit and push to GitHub")
    print("3. Visit your wiki to verify")


if __name__ == "__main__":
    main()
