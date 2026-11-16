@echo off
title Loki — Local-First AI Assistant
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_loki.ps1"
pause
