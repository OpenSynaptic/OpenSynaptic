# 处理zh_CN目录中的文件名冲突
$wikiPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki\zh_CN"

# 需要删除的重复文件（保留更新的版本）
$filesToDelete = @(
    "zh-guides-TUI_QUICK_REFERENCE_zh.md",
    "zh-guides-WEB_COMMANDS_REFERENCE_zh.md",
    "zh-Home.md"
)

$filesToDelete | ForEach-Object {
    $filePath = Join-Path $wikiPath $_
    if (Test-Path $filePath) {
        Write-Host "Deleting: $_"
        Remove-Item -Path $filePath -Force
    }
}

Write-Host "✓ 重复文件删除完成"

