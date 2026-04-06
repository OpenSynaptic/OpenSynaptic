#!/usr/bin/env python3
"""修复所有wiki markdown文件中的链接前缀"""
import os
import re
from pathlib import Path

wiki_base = Path(r"E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki")
zh_path = wiki_base / "zh_CN"
en_path = wiki_base / "en_GB"

# 用于zh_CN目录的替换规则
zh_replacements = [
    (r'\(zh-', '('),  # 移除zh-前缀
    (r'\[zh-', '['),  # 移除标题中的zh-前缀
    (r'\]\(Navigation-EN\)', '](../en_GB/Navigation-EN)'),  # 跨目录链接
    (r'\(en-', '(../en_GB/'),  # 将en-前缀转换为相对路径
]

# 用于en_GB目录的替换规则
en_replacements = [
    (r'\(en-', '('),  # 移除en-前缀
    (r'\[en-', '['),  # 移除标题中的en-前缀
    (r'\]\(Navigation-ZH\)', '](../zh_CN/Navigation-ZH)'),  # 跨目录链接
    (r'\(zh-', '(../zh_CN/'),  # 将zh-前缀转换为相对路径
]

def fix_links(directory, replacements):
    """处理目录中的所有md文件"""
    count = 0
    for md_file in directory.rglob("*.md"):
        content = md_file.read_text(encoding='utf-8')
        original_content = content
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            md_file.write_text(content, encoding='utf-8')
            print(f"✓ Fixed: {md_file.relative_to(wiki_base)}")
            count += 1
    
    return count

print("Fixing zh_CN links...")
zh_count = fix_links(zh_path, zh_replacements)
print(f"  Fixed {zh_count} files in zh_CN")

print("\nFixing en_GB links...")
en_count = fix_links(en_path, en_replacements)
print(f"  Fixed {en_count} files in en_GB")

print(f"\n✓ Total: {zh_count + en_count} files updated")

