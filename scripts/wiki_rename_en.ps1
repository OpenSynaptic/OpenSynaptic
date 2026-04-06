# 重命名en_GB目录中的所有文件，移除"en-"前缀
$wikiPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki\en_GB"

Get-ChildItem -Path $wikiPath -Filter "*.md" | ForEach-Object {
    $oldName = $_.Name
    $newName = $oldName

    # 移除"en-"前缀
    $newName = $newName -replace '^en-', ''

    if ($oldName -ne $newName) {
        $oldPath = Join-Path $wikiPath $oldName
        $newPath = Join-Path $wikiPath $newName

        Write-Host "Renaming: $oldName -> $newName"
        Rename-Item -Path $oldPath -NewName $newName -Force
    }
}

Write-Host "✓ en_GB目录重命名完成"

