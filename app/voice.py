"""Local-only Push-to-Talk Speech Recognition & Offline Text-to-Speech via Windows System.Speech."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from typing import Any

from app.config import load_settings


class LocalVoiceService:
    """
    Provides 100% local push-to-talk speech recognition and local text-to-speech
    using built-in Windows `.NET System.Speech` (zero cloud calls, zero audio uploads,
    never records continuously).
    """

    def __init__(self) -> None:
        self.is_listening: bool = False
        self.is_speaking: bool = False
        self._listen_proc: subprocess.Popen | None = None
        self._speak_proc: subprocess.Popen | None = None

    def get_status(self) -> dict[str, Any]:
        """Return current microphone/TTS state and installed offline Windows voices."""
        settings = load_settings()
        return {
            "local_only": True,
            "continuous_recording": False,
            "audio_uploaded": False,
            "is_listening": self.is_listening,
            "is_speaking": self.is_speaking,
            "selected_tts_voice": settings.get("selected_tts_voice", "Microsoft Zira Desktop"),
            "available_tts_voices": ["Microsoft Zira Desktop", "Microsoft David Desktop"],
            "recognizer_engine": "Windows System.Speech (MS-1033-80-DESK, Offline Push-to-Talk)",
            "tts_engine": "Windows System.Speech.Synthesis (Offline SAPI)",
        }

    def stop_listening(self) -> dict[str, Any]:
        """Immediately terminate an active push-to-talk microphone capture."""
        proc = self._listen_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self.is_listening = False
        self._listen_proc = None
        return {"ok": True, "is_listening": False}

    def stop_speaking(self) -> dict[str, Any]:
        """Immediately stop active local TTS playback."""
        proc = self._speak_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self.is_speaking = False
        self._speak_proc = None
        return {"ok": True, "is_speaking": False}

    async def listen_push_to_talk(self, timeout_seconds: int = 6) -> dict[str, Any]:
        """
        Capture a single spoken utterance via local Windows SpeechRecognitionEngine.
        Never records continuously and never writes audio files to disk or network.
        """
        if self.is_listening:
            return {"ok": False, "error": "Microphone is already active in Push-to-Talk mode."}

        safe_timeout = max(2, min(int(timeout_seconds), 12))
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "try { "
            "  $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
            "  $rec.SetInputToDefaultAudioDevice(); "
            "  $grammar = New-Object System.Speech.Recognition.DictationGrammar; "
            "  $rec.LoadGrammar($grammar); "
            f"  $res = $rec.Recognize([TimeSpan]::FromSeconds({safe_timeout})); "
            "  $rec.Dispose(); "
            "  if ($null -ne $res -and $res.Text) { "
            "    @{ ok = $true; text = $res.Text; confidence = [math]::Round($res.Confidence, 2) } | ConvertTo-Json -Compress "
            "  } else { "
            "    @{ ok = $false; error = 'No speech detected within the push-to-talk window.' } | ConvertTo-Json -Compress "
            "  } "
            "} catch { "
            "  @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress "
            "}"
        )

        self.is_listening = True
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
            )
            self._listen_proc = proc
            stdout, stderr = await asyncio.to_thread(proc.communicate, timeout=safe_timeout + 4)
            raw = (stdout or "").strip()
            if not raw:
                return {
                    "ok": False,
                    "error": (stderr or "").strip() or "Push-to-talk cancelled or timed out.",
                }
            parsed = json.loads(raw.splitlines()[-1])
            return parsed
        except Exception as exc:
            return {"ok": False, "error": f"Local push-to-talk error: {exc}"}
        finally:
            self.is_listening = False
            self._listen_proc = None

    async def speak_local_tts(self, text: str, voice_name: str | None = None) -> dict[str, Any]:
        """Speak text aloud locally using Windows System.Speech.Synthesis (offline)."""
        self.stop_speaking()
        clean_text = re.sub(r"[`#*_\[\]()>]", " ", str(text or "")).strip()
        clean_text = re.sub(r"\s+", " ", clean_text)[:900]
        if not clean_text:
            return {"ok": False, "error": "Nothing to speak."}

        settings = load_settings()
        voice = voice_name or str(settings.get("selected_tts_voice", "Microsoft Zira Desktop"))
        if voice not in ("Microsoft Zira Desktop", "Microsoft David Desktop"):
            voice = "Microsoft Zira Desktop"

        # Escape single quotes for PowerShell single-quoted string
        ps_text = clean_text.replace("'", "''")
        ps_voice = voice.replace("'", "''")
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"try {{ $s.SelectVoice('{ps_voice}') }} catch {{}}; "
            f"$s.Speak('{ps_text}'); "
            "$s.Dispose();"
        )

        self.is_speaking = True
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self._speak_proc = proc

            async def _watch() -> None:
                try:
                    await asyncio.to_thread(proc.wait)
                finally:
                    if self._speak_proc is proc:
                        self.is_speaking = False
                        self._speak_proc = None

            asyncio.create_task(_watch())
            return {
                "ok": True,
                "voice": voice,
                "chars_spoken": len(clean_text),
                "is_speaking": True,
            }
        except Exception as exc:
            self.is_speaking = False
            self._speak_proc = None
            return {"ok": False, "error": f"Local TTS error: {exc}"}


voice_service = LocalVoiceService()
