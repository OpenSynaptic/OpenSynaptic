#!/usr/bin/env python3
"""
Fix all broken links in the flattened wiki.
This script identifies and fixes common patterns in wiki links.
"""

import re
from pathlib import Path
from collections import defaultdict

WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")

# Build a mapping of all available pages
def build_page_index():
    """Build an index of all available wiki pages."""
    pages = {}
    
    for md_file in WIKI_BASE.glob("*.md"):
        page_name = md_file.stem
        pages[page_name] = md_file.name
    
    return pages


def fix_wiki_links():
    """Fix broken links in wiki files."""
    
    print("🔧 Fixing Broken Wiki Links")
    print("=" * 70)
    
    available_pages = build_page_index()
    print(f"\n📊 Found {len(available_pages)} pages in wiki")
    
    # Get all markdown files
    md_files = sorted([f for f in WIKI_BASE.glob("*.md") if f.is_file()])
    
    fixed_count = 0
    errors = []
    
    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                original_content = content
            
            # Get language from filename
            if md_file.stem.startswith("en-"):
                lang = "en"
                prefix = "en-"
            elif md_file.stem.startswith("zh-"):
                lang = "zh"
                prefix = "zh-"
            else:
                continue
            
            # Fix pattern 1: [text](guides-SOMETHING) -> [text](en-guides-SOMETHING)
            # But only if the target page doesn't match with language prefix
            def fix_subdir_links(match):
                text = match.group(1)
                link = match.group(2)
                
                # Skip if already has language prefix
                if link.startswith(("en-", "zh-")):
                    return match.group(0)
                
                # Check if this is a subdir link (e.g., guides-SOMETHING)
                if link in ("guides-", "api-", "plugins-", "reports-", "features-", "architecture-", "internal-", "releases-"):
                    # Category link, add language prefix
                    return f"[{text}]({prefix}{link})"
                
                # For other links, check if they exist with language prefix
                potential_page = f"{prefix}{link}"
                if potential_page in available_pages:
                    return f"[{text}]({potential_page})"
                
                return match.group(0)
            
            # Apply fixes
            pattern = r'\[([^\]]+)\]\(([^)#]+)\)'
            content = re.sub(pattern, fix_subdir_links, content)
            
            # Write back if changed
            if content != original_content:
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixed_count += 1
                print(f"  ✓ Fixed: {md_file.name}")
        
        except Exception as e:
            errors.append((md_file.name, str(e)))
            print(f"  ✗ Error in {md_file.name}: {e}")
    
    print(f"\n{'='*70}")
    print(f"✅ Fixed {fixed_count} files")
    if errors:
        print(f"⚠️  {len(errors)} files had errors")
    
    return fixed_count


def main():
    """Main entry point."""
    
    print("\n🎯 OpenSynaptic Wiki Link Fixing Tool\n")
    
    fixed = fix_wiki_links()
    
    print(f"\n{'='*70}")
    print(f"✨ Link fixing complete!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
