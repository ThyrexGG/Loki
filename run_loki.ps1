# Loki Launcher Script (Localhost-Only)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "=== Loki — Private Local-First AI Assistant ===" -ForegroundColor Cyan

# 1. Check if Ollama is listening on 127.0.0.1:11434; if not, start ollama.exe serve locally
$ollamaUrl = "http://127.0.0.1:11434/api/version"
$ollamaRunning = $false
try {
    $null = Invoke-RestMethod -Uri $ollamaUrl -TimeoutSec 2
    $ollamaRunning = $true
    Write-Host "[OK] Local Ollama daemon is already running on 127.0.0.1:11434" -ForegroundColor Green
} catch {
    $ollamaRunning = $false
}

if (-not $ollamaRunning) {
    $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaExe) {
        Write-Host "[INFO] Starting local Ollama daemon (127.0.0.1:11434)..." -ForegroundColor Yellow
        $env:OLLAMA_HOST = "127.0.0.1:11434"
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[WARN] Ollama binary not found at $ollamaExe. Please start Ollama manually." -ForegroundColor Yellow
    }
}

Write-Host "[INFO] Starting Loki web server at http://127.0.0.1:8420 ..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop Loki." -ForegroundColor Gray
$pythonExe = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "py" }
& $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8420
