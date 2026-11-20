"""Local-only Push-to-Talk Speech Recognition & Offline Text-to-Speech via Windows System.Speech."""

from __future__ import annotations

import asyncio
import collections
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, load_settings

HANDSFREE_SCRIPT = Path(__file__).resolve().parent / "voice_handsfree.ps1"
PAUSE_FILE = DATA_DIR / "voice_speaking.flag"


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
        # Hands-free ("Hey Loki"): off unless the user switches it on; never survives a restart.
        self._hf_proc: subprocess.Popen | None = None
        self._hf_events: collections.deque = collections.deque(maxlen=50)
        self._hf_seq = 0
        self._hf_lock = threading.Lock()
        self._hf_error = ""

    # ---- Hands-free -----------------------------------------------------------------
    @property
    def handsfree_on(self) -> bool:
        return bool(self._hf_proc and self._hf_proc.poll() is None)

    def _hf_push(self, event: dict[str, Any]) -> None:
        with self._hf_lock:
            self._hf_seq += 1
            self._hf_events.append({**event, "seq": self._hf_seq, "time": time.time()})

    def _hf_reader(self, proc: subprocess.Popen) -> None:
        for line in iter(proc.stdout.readline, ""):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "error":
                self._hf_error = str(ev.get("error") or "")[:300]
            self._hf_push(ev)
        if self._hf_proc is proc:
            self._hf_push({"event": "stopped", "error": self._hf_error})
            self._hf_proc = None

    def start_handsfree(self) -> dict[str, Any]:
        if self.handsfree_on:
            return {"ok": True, "handsfree": True}
        self._hf_error = ""
        PAUSE_FILE.unlink(missing_ok=True)
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                 str(HANDSFREE_SCRIPT), "-PauseFile", str(PAUSE_FILE)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        except OSError as exc:
            return {"ok": False, "error": f"Could not start the microphone listener: {exc}"}
        self._hf_proc = proc
        threading.Thread(target=self._hf_reader, args=(proc,), daemon=True).start()
        return {"ok": True, "handsfree": True}

    def stop_handsfree(self) -> dict[str, Any]:
        proc, self._hf_proc = self._hf_proc, None
        if proc and proc.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        PAUSE_FILE.unlink(missing_ok=True)
        return {"ok": True, "handsfree": False}

    def poll_handsfree(self, after: int = 0) -> dict[str, Any]:
        with self._hf_lock:
            events = [e for e in self._hf_events if e["seq"] > after]
        return {"handsfree": self.handsfree_on, "events": events, "last_seq": self._hf_seq,
                "is_speaking": self.is_speaking, "error": self._hf_error}

    def get_status(self) -> dict[str, Any]:
        """Return current microphone/TTS state and installed offline Windows voices."""
        settings = load_settings()
        return {
            "local_only": True,
            "continuous_recording": False,
            "audio_uploaded": False,
            "is_listening": self.is_listening,
            "is_speaking": self.is_speaking,
            "handsfree": self.handsfree_on,
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
        PAUSE_FILE.unlink(missing_ok=True)
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
        clean_text = re.sub(r"```.*?```", " (code shown on screen) ", str(text or ""), flags=re.S)
        clean_text = re.sub(r"https?://\S+", " ", clean_text)
        clean_text = re.sub(r"[`#*_\[\]()>|]", " ", clean_text).strip()
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
        if self.handsfree_on:
            try:
                PAUSE_FILE.write_text("speaking", encoding="utf-8")  # the listener must not hear Loki itself
            except OSError:
                pass
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
                        await asyncio.sleep(0.4)  # let the room go quiet before listening again
                        if not self.is_speaking:
                            PAUSE_FILE.unlink(missing_ok=True)

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
