#!/usr/bin/env python3
"""
Fix language links and internal references in migrated wiki files.
"""

import re
from pathlib import Path

WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")

def fix_language_links(content: str, filename: str) -> str:
    """
    Fix language links in wiki files.
    Ensures that cross-language references are properly prefixed.
    """
    
    # Determine language from filename
    if filename.startswith("en-"):
        current_lang = "en"
        other_lang = "zh"
    elif filename.startswith("zh-"):
        current_lang = "zh"
        other_lang = "en"
    else:
        return content
    
    # Fix: [English](INDEX) -> [English](en-INDEX)
    # Fix: [中文](INDEX) -> [中文](zh-INDEX)
    if current_lang == "en":
        # In English files, fix references to INDEX to en-INDEX
        content = re.sub(r'\[English\]\(INDEX\)', r'[English](en-INDEX)', content)
        content = re.sub(r'\[中文\]\(INDEX(?!\.md)\)', r'[中文](zh-INDEX)', content)
        # Fix ../zh/INDEX.md -> zh-INDEX
        content = re.sub(r'\(\.\./zh/INDEX\.md\)', r'(zh-INDEX)', content)
    elif current_lang == "zh":
        # In Chinese files, fix references to INDEX to zh-INDEX
        content = re.sub(r'\[English\]\(INDEX(?!\.md)\)', r'[English](en-INDEX)', content)
        content = re.sub(r'\[中文\]\(INDEX\)', r'[中文](zh-INDEX)', content)
        # Fix ../en/INDEX.md -> en-INDEX
        content = re.sub(r'\(\.\./en/INDEX\.md\)', r'(en-INDEX)', content)
    
    return content


def process_wiki_files():
    """Process all wiki files to fix language links."""
    
    print("Fixing language links in wiki files...")
    
    fixed_count = 0
    
    # Process all .md files in root
    for md_file in sorted(WIKI_BASE.glob("*.md")):
        # Skip special files
        if md_file.name.startswith("_") or md_file.name == "Home.md":
            continue
        
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            content = fix_language_links(content, md_file.stem)
            
            if content != original_content:
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixed_count += 1
                print(f"  ✓ Fixed: {md_file.name}")
        
        except Exception as e:
            print(f"  ✗ Error processing {md_file.name}: {e}")
    
    print(f"\n✓ Fixed {fixed_count} files")


def main():
    """Main entry point."""
    print("OpenSynaptic Wiki Link Fixer")
    print("=" * 60)
    
    process_wiki_files()
    
    print("\n✓ Link fixing complete!")


if __name__ == "__main__":
    main()
