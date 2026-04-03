#!/usr/bin/env python3
"""
Flatten GitHub Wiki structure - move all files from subdirectories to root.
This improves navigation and makes the wiki easier to manage.
"""

import os
import shutil
from pathlib import Path

WIKI_BASE = Path("OpenSynaptic_Wiki/OpenSynaptic.wiki")

def flatten_wiki():
    """Move all files from subdirectories to root directory."""
    
    print("Flattening GitHub Wiki structure...")
    print("=" * 60)
    
    moved_count = 0
    error_count = 0
    
    # Get all subdirectories
    subdirs = [d for d in WIKI_BASE.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    for subdir in sorted(subdirs):
        print(f"\nProcessing: {subdir.name}/")
        
        # Get all .md files in this subdirectory
        for md_file in sorted(subdir.glob("*.md")):
            try:
                # Create new filename: prefix-subdir-filename
                # Example: en-guides/DISPLAY_API_GUIDE.md -> en-guides-DISPLAY_API_GUIDE.md
                parent_prefix = subdir.name
                new_filename = f"{parent_prefix}-{md_file.name}"
                new_path = WIKI_BASE / new_filename
                
                # Move the file
                shutil.move(str(md_file), str(new_path))
                print(f"  ✓ Moved: {subdir.name}/{md_file.name} -> {new_filename}")
                moved_count += 1
            
            except Exception as e:
                print(f"  ✗ Error moving {md_file.name}: {e}")
                error_count += 1
        
        # Check if subdirectory has nested directories (e.g., en-guides/drivers/)
        nested_dirs = [d for d in subdir.iterdir() if d.is_dir()]
        for nested_dir in sorted(nested_dirs):
            print(f"  Processing nested: {nested_dir.name}/")
            
            for md_file in sorted(nested_dir.glob("*.md")):
                try:
                    # Example: en-api/drivers/bidirectional-capability.md 
                    # -> en-api-drivers-bidirectional-capability.md
                    new_filename = f"{parent_prefix}-{nested_dir.name}-{md_file.name}"
                    new_path = WIKI_BASE / new_filename
                    
                    shutil.move(str(md_file), str(new_path))
                    print(f"    ✓ Moved: {subdir.name}/{nested_dir.name}/{md_file.name} -> {new_filename}")
                    moved_count += 1
                
                except Exception as e:
                    print(f"    ✗ Error moving {md_file.name}: {e}")
                    error_count += 1
    
    # Remove empty subdirectories
    print("\n\nRemoving empty directories...")
    for subdir in WIKI_BASE.iterdir():
        if subdir.is_dir() and not subdir.name.startswith('.'):
            try:
                # Check if directory is empty
                if not any(subdir.iterdir()):
                    subdir.rmdir()
                    print(f"  ✓ Removed: {subdir.name}/")
            except Exception as e:
                # Directory might not be empty, that's ok
                pass
    
    print("\n" + "=" * 60)
    print(f"Flattening complete!")
    print(f"Files moved: {moved_count}")
    print(f"Errors: {error_count}")
    
    return moved_count, error_count


def verify_structure():
    """Verify the flattened structure."""
    
    print("\n\nVerifying flattened structure...")
    print("=" * 60)
    
    # Count files
    md_files = list(WIKI_BASE.glob("*.md"))
    subdirs = [d for d in WIKI_BASE.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    print(f"\nTotal markdown files in root: {len(md_files)}")
    print(f"Remaining subdirectories (should be empty): {len(subdirs)}")
    
    if subdirs:
        print("\nRemaining subdirectories:")
        for subdir in sorted(subdirs):
            files = list(subdir.glob("**/*.md"))
            print(f"  {subdir.name}/ ({len(files)} files)")
    
    # Show sample of root files
    print("\nSample of root files:")
    for f in sorted(md_files)[:20]:
        print(f"  - {f.name}")
    
    if len(md_files) > 20:
        print(f"  ... and {len(md_files) - 20} more")


def main():
    """Main entry point."""
    
    print("OpenSynaptic Wiki Flattening Tool")
    print("=" * 60)
    print(f"Wiki location: {WIKI_BASE}")
    print()
    
    # Perform flattening
    moved, errors = flatten_wiki()
    
    # Verify
    verify_structure()
    
    print("\n✓ Flattening complete!")
    print("\nNext steps:")
    print("1. Update _Sidebar.md with new flattened structure")
    print("2. Update Home.md with proper navigation")
    print("3. Test all links")


if __name__ == "__main__":
    main()
