# 重命名zh_CN目录中的所有文件，移除"zh-"前缀和"_zh"后缀
$wikiPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki\zh_CN"

Get-ChildItem -Path $wikiPath -Filter "*.md" | ForEach-Object {
    $oldName = $_.Name
    $newName = $oldName

    # 移除"zh-"前缀
    $newName = $newName -replace '^zh-', ''

    # 移除"_zh"后缀（在.md之前）
    $newName = $newName -replace '_zh(?=\.md$)', ''

    # 特殊处理：zh-Home.md -> Home.md（将覆盖旧的Home.md）
    if ($oldName -eq "zh-Home.md") {
        $newName = "Home.md"
    }

    # 特殊处理：zh-INDEX.md -> INDEX.md（将覆盖旧的INDEX.md）
    if ($oldName -eq "zh-INDEX.md") {
        $newName = "INDEX.md"
    }

    if ($oldName -ne $newName) {
        $oldPath = Join-Path $wikiPath $oldName
        $newPath = Join-Path $wikiPath $newName

        Write-Host "Renaming: $oldName -> $newName"
        Rename-Item -Path $oldPath -NewName $newName -Force
    }
}

Write-Host "✓ zh_CN目录重命名完成"

