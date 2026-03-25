param(
    [string]$CommandName = "os-node",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command register-python-argcomplete -ErrorAction SilentlyContinue)) {
    Write-Error "register-python-argcomplete not found. Install dependency first: py -3 -m pip install argcomplete"
}

$profilePath = $PROFILE.CurrentUserAllHosts
$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

$line = "Invoke-Expression (register-python-argcomplete $CommandName --shell powershell)"
$content = Get-Content -Path $profilePath -Raw -ErrorAction SilentlyContinue
if ($content -and $content.Contains($line) -and -not $Force) {
    Write-Host "Argcomplete activation line already present in $profilePath"
    exit 0
}

if (-not [string]::IsNullOrWhiteSpace($content)) {
    Add-Content -Path $profilePath -Value "`n$line"
} else {
    Set-Content -Path $profilePath -Value $line
}

Write-Host "Argcomplete enabled for '$CommandName'. Restart PowerShell to apply."
Write-Host "Profile: $profilePath"

