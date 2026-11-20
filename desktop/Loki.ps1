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

# Fast "is anything listening?" probe. A refused HTTP request to localhost takes ~2 s on Windows;
# this answers in well under half a second, so the launcher only does the HTTP check once the port is open.
function Test-Port([int]$port, [int]$ms = 300) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { return ($c.ConnectAsync('127.0.0.1', $port).Wait($ms) -and $c.Connected) } catch { return $false } finally { $c.Close() }
}

function Test-Loki { (Test-Port 8420) -and (Test-Url "$Url/static/loki.png" 3) }

# Small "Starting Loki..." splash so a click on the taskbar icon gives instant feedback while the server boots.
$script:Splash = $null
function Show-Splash {
    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        $f = New-Object System.Windows.Forms.Form
        $f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.Size = New-Object System.Drawing.Size(320, 200)
        $f.BackColor = [System.Drawing.Color]::FromArgb(20, 20, 22); $f.TopMost = $true; $f.ShowInTaskbar = $false
        $logo = Join-Path $Root 'static\loki.png'
        if (Test-Path $logo) {
            $pb = New-Object System.Windows.Forms.PictureBox
            $pb.Image = [System.Drawing.Image]::FromFile($logo); $pb.SizeMode = 'Zoom'
            $pb.Size = New-Object System.Drawing.Size(84, 84); $pb.Location = New-Object System.Drawing.Point(118, 34)
            $f.Controls.Add($pb)
        }
        $lb = New-Object System.Windows.Forms.Label
        $lb.Text = 'Starting Loki...'; $lb.ForeColor = [System.Drawing.Color]::FromArgb(225, 225, 230)
        $lb.Font = New-Object System.Drawing.Font('Segoe UI', 11); $lb.TextAlign = 'MiddleCenter'
        $lb.Size = New-Object System.Drawing.Size(320, 30); $lb.Location = New-Object System.Drawing.Point(0, 134)
        $f.Controls.Add($lb)
        $f.Show(); [System.Windows.Forms.Application]::DoEvents()
        $script:Splash = $f
    } catch { $script:Splash = $null }
}
function Close-Splash { if ($script:Splash) { try { $script:Splash.Close(); $script:Splash.Dispose() } catch {}; $script:Splash = $null } }
# Wait while keeping the splash responsive.
function Wait-Ui([int]$ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    do {
        if ($script:Splash) { [System.Windows.Forms.Application]::DoEvents() }
        Start-Sleep -Milliseconds 50
    } while ((Get-Date) -lt $end)
}

function Show-Error([string]$msg) {
    Close-Splash
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($msg, 'Loki', 'OK', 'Error') | Out-Null
}

if (-not (Test-Port 8420)) { Show-Splash }

# 1. Local Ollama daemon (uses OLLAMA_MODELS if you set it, otherwise Ollama's default folder)
if (-not ((Test-Port 11434) -and (Test-Url 'http://127.0.0.1:11434/api/version' 4))) {
    if (Test-Path $OllamaExe) {
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        if (Test-Path 'D:\OllamaModels') { $env:OLLAMA_MODELS = 'D:\OllamaModels' }
        Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden
    }
}

# 2. Loki server (hidden, bound to 127.0.0.1 only)
$server = $null
$ready = Test-Loki
if (-not $ready) {
    if (-not (Test-Path $PythonExe)) { Show-Error "Python not found at $PythonExe"; exit 1 }
    # If another uvicorn is already starting up on port 8420, wait up to 12s for it before spawning a second one
    $existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'uvicorn.*8420' }
    if ($existing) {
        $waitExisting = (Get-Date).AddSeconds(12)
        while (-not ($ready = Test-Loki) -and (Get-Date) -lt $waitExisting) {
            Wait-Ui 300
        }
    }
}
if (-not $ready) {
    # Stop any hung uvicorn process still holding port 8420 so bind never fails with WinError 10048
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'uvicorn.*8420' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Wait-Ui 300
    $server = Start-Process -FilePath $PythonExe `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8420' `
        -WorkingDirectory $Root -NoNewWindow -PassThru `
        -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err"
    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Loki)) {
        if ((Get-Date) -gt $deadline) {
            Show-Error "Loki server failed to start. See $LogFile.err"
            exit 1
        }
        if ($server.HasExited) {
            Wait-Ui 2000
            if (Test-Loki) { break }
            Show-Error "Loki server failed to start. See $LogFile.err"
            exit 1
        }
        Wait-Ui 250
    }
}

# 3. App window (Edge app mode; falls back to Chrome)
$browser = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) { Close-Splash; Start-Process $Url; exit 0 }

# Clear any lingering headless/hidden Edge processes holding $AppProfile so the new window always opens visibly
$staleEdge = Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape($AppProfile) }
if ($staleEdge) {
    $hasVisible = $false
    foreach ($ep in $staleEdge) {
        $pObj = Get-Process -Id $ep.ProcessId -ErrorAction SilentlyContinue
        if ($pObj -and $pObj.MainWindowHandle -ne [IntPtr]::Zero) { $hasVisible = $true }
    }
    if (-not $hasVisible) {
        foreach ($ep in $staleEdge) { Stop-Process -Id $ep.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 400
    }
}

# Fresh UI after every Loki update: clear the app window's page cache when no Loki window is open
# (an old cached index.html kept showing the previous UI). Settings, sign-ins and storage are kept.
$profileInUse = Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape($AppProfile) }
if (-not $profileInUse) {
    foreach ($d in 'Cache', 'Code Cache') {
        Remove-Item -LiteralPath (Join-Path $AppProfile "Default\$d") -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$window = Start-Process -FilePath $browser -WindowStyle Normal -PassThru -ArgumentList @(
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
            Close-Splash
            [LokiShell]::BringToFront($window.MainWindowHandle)
            break
        }
        Wait-Ui 200
    }
} catch {
    Add-Content -Path $LogFile -Value "[desktop] could not set taskbar identity: $($_.Exception.Message)"
}
Close-Splash

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
