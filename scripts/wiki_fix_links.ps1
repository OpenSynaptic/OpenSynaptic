# PowerShell脚本来修复所有markdown文件中的链接前缀

# zh_CN目录
$zhPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki\zh_CN"
# en_GB目录
$enPath = "E:\新建文件夹 (2)\OpenSynaptic_Wiki\OpenSynaptic.wiki\en_GB"

# 需要替换的链接对（旧格式 -> 新格式）
$replacements = @(
    # 为zh_CN修复的链接
    @{ old = "zh-Home"; new = "Home"; dir = $zhPath }
    @{ old = "zh-README"; new = "README"; dir = $zhPath }
    @{ old = "zh-ARCHITECTURE"; new = "ARCHITECTURE"; dir = $zhPath }
    @{ old = "zh-QUICK_START"; new = "QUICK_START"; dir = $zhPath }
    @{ old = "zh-INDEX"; new = "INDEX"; dir = $zhPath }
    @{ old = "en-README"; new = "../en_GB/README"; dir = $zhPath }
    @{ old = "en-ARCHITECTURE"; new = "../en_GB/ARCHITECTURE"; dir = $zhPath }
    @{ old = "en-QUICK_START"; new = "../en_GB/QUICK_START"; dir = $zhPath }
    @{ old = "en-plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026"; new = "../en_GB/plugins-PLUGIN_DEVELOPMENT_SPECIFICATION_2026"; dir = $zhPath }
    @{ old = "Navigation-EN"; new = "../en_GB/Navigation-EN"; dir = $zhPath }

    # 为en_GB修复的链接
    @{ old = "en-Home"; new = "Home"; dir = $enPath }
    @{ old = "en-README"; new = "README"; dir = $enPath }
    @{ old = "en-ARCHITECTURE"; new = "ARCHITECTURE"; dir = $enPath }
    @{ old = "en-QUICK_START"; new = "QUICK_START"; dir = $enPath }
    @{ old = "en-INDEX"; new = "INDEX"; dir = $enPath }
    @{ old = "zh-README"; new = "../zh_CN/README"; dir = $enPath }
    @{ old = "zh-ARCHITECTURE"; new = "../zh_CN/ARCHITECTURE"; dir = $enPath }
    @{ old = "Navigation-ZH"; new = "../zh_CN/Navigation-ZH"; dir = $enPath }
)

# 处理 Home.md 和其他关键文件
Get-ChildItem -Path $zhPath -Filter "Home.md" | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    $originalContent = $content

    foreach ($replacement in $replacements) {
        if ($replacement.dir -eq $zhPath) {
            $pattern = "href=`"$($replacement.old)`""
            $newPattern = "href=`"$($replacement.new)`""
            $content = $content -replace $pattern, $newPattern
        }
    }

    if ($content -ne $originalContent) {
        Set-Content -Path $_.FullName -Value $content
        Write-Host "Updated: zh_CN/$($_.Name)"
    }
}

# 处理 en_GB Home.md
Get-ChildItem -Path $enPath -Filter "Home.md" | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    $originalContent = $content

    foreach ($replacement in $replacements) {
        if ($replacement.dir -eq $enPath) {
            $pattern = "href=`"$($replacement.old)`""
            $newPattern = "href=`"$($replacement.new)`""
            $content = $content -replace $pattern, $newPattern
        }
    }

    if ($content -ne $originalContent) {
        Set-Content -Path $_.FullName -Value $content
        Write-Host "Updated: en_GB/$($_.Name)"
    }
}

Write-Host "✓ 链接修复完成"

