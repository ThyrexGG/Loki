# Loki Desktop App launcher (localhost-only, zero new dependencies).
# Opens Loki in its own Microsoft Edge app window (no tabs / address bar), with a dedicated
# browser profile kept inside D:\Loki\desktop\profile. Starts Ollama and the Loki server if
# they are not already running, and when the window is closed it unloads the model from VRAM
# and stops the server it started (a server you started yourself is left running).
$ErrorActionPreference = 'Stop'
$Root      = Split-Path $PSScriptRoot -Parent
$Url       = 'http://127.0.0.1:8420'
$PythonExe = Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'
if (-not (Test-Path $PythonExe)) {
    $found = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($found) { $PythonExe = $found.Source }
}
$OllamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$AppProfile = Join-Path $PSScriptRoot 'profile'
$LogFile   = Join-Path $PSScriptRoot 'server.log'

function Test-Url([string]$u, [int]$timeout = 2) {
    try { $null = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec $timeout; return $true } catch { return $false }
}

function Show-Error([string]$msg) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($msg, 'Loki', 'OK', 'Error') | Out-Null
}

# 1. Local Ollama daemon (uses OLLAMA_MODELS if you set it, otherwise Ollama's default folder)
if (-not (Test-Url 'http://127.0.0.1:11434/api/version')) {
    if (Test-Path $OllamaExe) {
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden
    }
}

# 2. Loki server (hidden, bound to 127.0.0.1 only)
$server = $null
if (-not (Test-Url "$Url/static/loki.png")) {
    if (-not (Test-Path $PythonExe)) { Show-Error "Python not found at $PythonExe"; exit 1 }
    $server = Start-Process -FilePath $PythonExe `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8420' `
        -WorkingDirectory $Root -NoNewWindow -PassThru `
        -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err"
    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Url "$Url/static/loki.png")) {
        if ($server.HasExited -or (Get-Date) -gt $deadline) {
            Show-Error "Loki server failed to start. See $LogFile.err"
            exit 1
        }
        Start-Sleep -Milliseconds 400
    }
}

# 3. App window (Edge app mode; falls back to Chrome)
$browser = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) { Start-Process $Url; exit 0 }

$window = Start-Process -FilePath $browser -PassThru -ArgumentList @(
    "--app=$Url", "--user-data-dir=`"$AppProfile`"", '--window-size=1320,880',
    '--no-first-run', '--no-default-browser-check', '--disable-sync'
)
# Give the window Loki's own taskbar identity (AppUserModelID shared with the shortcuts) and icon,
# so Windows shows the Loki icon instead of grouping it under Microsoft Edge.
$AppId = 'Loki.LocalAI'
try {
    Add-Type -Path (Join-Path $PSScriptRoot 'LokiShell.cs') -ErrorAction Stop
    # Same content-hashed icon copy the shortcuts use (see Install_Shortcuts.ps1); falls back to loki.ico.
    $ico = Join-Path $PSScriptRoot 'loki.ico'
    $hashed = Join-Path $PSScriptRoot ("icons\loki-{0}.ico" -f (Get-FileHash $ico -Algorithm SHA256).Hash.Substring(0, 10).ToLower())
    if (Test-Path $hashed) { $ico = $hashed }
    $relaunch = "`"$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and -not $window.HasExited) {
        $window.Refresh()
        if ($window.MainWindowHandle -ne [IntPtr]::Zero) {
            [LokiShell]::SetWindowAppId($window.MainWindowHandle, $AppId, $relaunch, $ico, 'Loki')
            [LokiShell]::SetWindowIcon($window.MainWindowHandle, $ico)
            break
        }
        Start-Sleep -Milliseconds 200
    }
} catch {
    Add-Content -Path $LogFile -Value "[desktop] could not set taskbar identity: $($_.Exception.Message)"
}

$window.WaitForExit()

# 4. Window closed: free VRAM and stop the server we started.
if ($server -and -not $server.HasExited) {
    try {
        $model = (Get-Content (Join-Path $Root 'data\settings.json') -Raw | ConvertFrom-Json).selected_model
        $body = @{ model = $model } | ConvertTo-Json
        $null = Invoke-RestMethod -Uri "$Url/api/ollama/unload" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
    } catch {}
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
