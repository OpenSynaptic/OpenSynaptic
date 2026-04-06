# 全面的链接修复脚本 - 处理所有md文件
$wikiPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki"

# 处理zh_CN目录中的所有markdown文件
$zhPath = "$wikiPath\zh_CN"
Get-ChildItem -Path $zhPath -Filter "*.md" -Recurse | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    $originalContent = $content

    # 替换所有的en-前缀为相对路径
    $content = $content -replace '\]\(en-', '](../en_GB/')
    $content = $content -replace '\[en-([^\]]+)\]', '[$1]'

    # 替换所有的zh-前缀（在md文件内部）
    $content = $content -replace '\]\(zh-', ']('
    $content = $content -replace 'zh-Navigation-ZH', 'Navigation-ZH'

    if ($content -ne $originalContent) {
        Set-Content -Path $_.FullName -Value $content
        Write-Host "Fixed: zh_CN/$($_.Name)"
    }
}

# 处理en_GB目录中的所有markdown文件
$enPath = "$wikiPath\en_GB"
Get-ChildItem -Path $enPath -Filter "*.md" -Recurse | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    $originalContent = $content

    # 替换所有的zh-前缀为相对路径
    $content = $content -replace '\]\(zh-', '](../zh_CN/'
    $content = $content -replace '\[zh-([^\]]+)\]', '[$1]'

    # 保留en-前缀的移除（但要检查是否已经移除了）
    # 这里我们保持简单，因为文件名已经改了

    if ($content -ne $originalContent) {
        Set-Content -Path $_.FullName -Value $content
        Write-Host "Fixed: en_GB/$($_.Name)"
    }
}

Write-Host "✓ 所有链接修复完成"

