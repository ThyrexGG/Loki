# Loki hands-free listener (offline, Windows System.Speech). Started only while the user has Hands-free on.
# Waits for the wake phrase ("Hey Loki"), then captures one spoken request with dictation and prints it as a
# JSON line. Audio is processed in memory by Windows' own engine: nothing is recorded to disk or sent anywhere.
# While $PauseFile exists (Loki is speaking), recognition is paused so Loki does not hear itself.
param([string]$PauseFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Out-Event($obj) { [Console]::Out.WriteLine(($obj | ConvertTo-Json -Compress)); [Console]::Out.Flush() }

try {
    Add-Type -AssemblyName System.Speech
    $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    $rec.SetInputToDefaultAudioDevice()
    $choices = New-Object System.Speech.Recognition.Choices
    $choices.Add([string[]]@('hey loki', 'okay loki', 'ok loki', 'hi loki'))
    $gb = New-Object System.Speech.Recognition.GrammarBuilder
    $gb.Append($choices)
    $wake = New-Object System.Speech.Recognition.Grammar($gb)
    $wake.Name = 'wake'
    $dictation = New-Object System.Speech.Recognition.DictationGrammar
    $dictation.Name = 'dictation'
    $rec.LoadGrammar($wake)
    Out-Event @{ event = 'ready' }
} catch {
    Out-Event @{ event = 'error'; error = $_.Exception.Message }
    exit 1
}

while ($true) {
    if ($PauseFile -and (Test-Path $PauseFile)) { Start-Sleep -Milliseconds 300; continue }
    try {
        $res = $rec.Recognize([TimeSpan]::FromSeconds(3))
    } catch {
        Out-Event @{ event = 'error'; error = $_.Exception.Message }
        Start-Sleep -Seconds 2
        continue
    }
    if ($null -eq $res -or $res.Grammar.Name -ne 'wake' -or $res.Confidence -lt 0.55) { continue }
    if ($PauseFile -and (Test-Path $PauseFile)) { continue }
    Out-Event @{ event = 'wake'; confidence = [math]::Round($res.Confidence, 2) }
    $rec.UnloadGrammar($wake)
    $rec.LoadGrammar($dictation)
    try {
        $rec.InitialSilenceTimeout = [TimeSpan]::FromSeconds(6)
        $rec.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.2)
        $said = $rec.Recognize([TimeSpan]::FromSeconds(14))
        if ($null -ne $said -and $said.Text) {
            Out-Event @{ event = 'heard'; text = $said.Text; confidence = [math]::Round($said.Confidence, 2) }
        } else {
            Out-Event @{ event = 'nothing' }
        }
    } catch {
        Out-Event @{ event = 'error'; error = $_.Exception.Message }
    } finally {
        $rec.UnloadGrammar($dictation)
        $rec.LoadGrammar($wake)
    }
}
