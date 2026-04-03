#!/usr/bin/env python3
"""
Verify all links in the flattened wiki are valid.
"""

import re
from pathlib import Path
from collections import defaultdict

WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")

def check_wiki_links():
    """Check all wiki links for validity."""
    
    print("🔍 Verifying Wiki Links")
    print("=" * 70)
    
    # Get all markdown files
    md_files = sorted([f for f in WIKI_BASE.glob("*.md") if f.is_file()])
    
    # Build index of available pages
    available_pages = set()
    for md_file in md_files:
        page_name = md_file.stem
        available_pages.add(page_name)
    
    print(f"\n📊 Found {len(available_pages)} pages in wiki\n")
    
    # Pattern for markdown links
    link_pattern = r'\[([^\]]+)\]\(([^)#]+)(?:#([^)]*))?\)'
    
    broken_links = defaultdict(list)
    internal_links = 0
    external_links = 0
    valid_internal_links = 0
    
    # Check each file
    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all links
            for match in re.finditer(link_pattern, content):
                text = match.group(1)
                url = match.group(2)
                anchor = match.group(3)
                
                # Skip external links and anchors-only
                if url.startswith(('http://', 'https://', 'ftp://', 'mailto:')):
                    external_links += 1
                    continue
                
                if not url:  # Anchor-only link
                    continue
                
                # Check internal links
                internal_links += 1
                
                if url in available_pages:
                    valid_internal_links += 1
                else:
                    broken_links[md_file.name].append({
                        'text': text,
                        'url': url,
                        'anchor': anchor,
                        'line_num': content[:match.start()].count('\n') + 1
                    })
        
        except Exception as e:
            print(f"⚠️  Error reading {md_file.name}: {e}")
    
    # Report results
    print(f"✅ Valid internal links: {valid_internal_links}")
    print(f"🌐 External links: {external_links}")
    print(f"📌 Total internal links: {internal_links}")
    
    if broken_links:
        print(f"\n❌ Found {sum(len(v) for v in broken_links.values())} broken links:\n")
        
        for filename, links in sorted(broken_links.items()):
            print(f"  📄 {filename}")
            for link in links:
                print(f"    Line {link['line_num']:3d}: [{link['text']}]({link['url']})")
                if link['anchor']:
                    print(f"              └─ anchor: #{link['anchor']}")
    else:
        print(f"\n✅ All {internal_links} internal links are valid!")
    
    # Statistics
    print(f"\n{'='*70}")
    print(f"📈 Wiki Statistics")
    print(f"{'='*70}")
    print(f"Total Pages:              {len(available_pages)}")
    print(f"Total Links:              {internal_links + external_links}")
    print(f"  ├─ Internal:            {internal_links}")
    print(f"  ├─ Valid:               {valid_internal_links}")
    print(f"  ├─ Broken:              {internal_links - valid_internal_links}")
    print(f"  └─ External:            {external_links}")
    print(f"\nLink Integrity:           {100*valid_internal_links//internal_links if internal_links > 0 else 0}%")
    
    return len(broken_links) == 0


def main():
    """Main entry point."""
    
    print("\n🎯 OpenSynaptic Wiki Link Verification Tool\n")
    
    all_valid = check_wiki_links()
    
    print(f"\n{'='*70}")
    if all_valid:
        print("✅ All links verified successfully!")
        print("\n✨ Wiki is ready for use!")
    else:
        print("⚠️  Some links need attention before publishing.")
    
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
