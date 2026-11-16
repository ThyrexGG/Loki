# Creates "Loki" shortcuts on the Desktop and in the Start Menu that launch desktop\Loki.ps1
# in a hidden PowerShell window. Re-run any time; existing Loki shortcuts are replaced.
# To remove: delete "Loki.lnk" from your Desktop and from
#   %APPDATA%\Microsoft\Windows\Start Menu\Programs
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'Loki.ps1'
# Windows caches shortcut/taskbar icons by file path, so point shortcuts at a copy whose name contains
# the icon's content hash (icons\loki-<hash>.ico). A changed loki.ico gets a new path and shows at once.
$src      = Join-Path $PSScriptRoot 'loki.ico'
$hash     = (Get-FileHash $src -Algorithm SHA256).Hash.Substring(0, 10).ToLower()
$iconDir  = Join-Path $PSScriptRoot 'icons'
New-Item -ItemType Directory -Force $iconDir | Out-Null
Get-ChildItem $iconDir -Filter 'loki-*.ico' | Where-Object { $_.Name -ne "loki-$hash.ico" } | Remove-Item -Force -ErrorAction SilentlyContinue
$icon     = Join-Path $iconDir "loki-$hash.ico"
if (-not (Test-Path $icon)) { Copy-Item $src $icon }
$shell    = New-Object -ComObject WScript.Shell
$AppId    = 'Loki.LocalAI'   # must match Loki.ps1 so the taskbar shows Loki's icon, not Edge's
Add-Type -Path (Join-Path $PSScriptRoot 'LokiShell.cs')

$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Loki.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Loki.lnk')
)
foreach ($path in $targets) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath       = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $lnk.Arguments        = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
    $lnk.WorkingDirectory = $PSScriptRoot
    $lnk.IconLocation     = "$icon,0"
    $lnk.WindowStyle      = 7   # start minimized so no console flashes
    $lnk.Description      = 'Loki - private local AI assistant'
    $lnk.Save()
    [LokiShell]::SetShortcutAppId($path, $AppId)
    Write-Host "Created $path"
}
