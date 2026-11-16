"""Narrowly scoped, explicit read-only system health and diagnostics collectors for Windows."""

from __future__ import annotations

import ctypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ensure_data_dir

_CPU_NAME: str | None = None


def _cpu_name() -> str:
    """Processor name from the registry (read-only), cached."""
    global _CPU_NAME
    if _CPU_NAME is None:
        import os
        import platform

        name = ""
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                name = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except (OSError, ImportError):
            name = platform.processor()
        threads = os.cpu_count()
        _CPU_NAME = f"{name or 'Unknown CPU'}" + (f" ({threads} threads)" if threads else "")
    return _CPU_NAME

ALLOWED_LOG_EXTENSIONS = {".log", ".txt", ".out", ".err", ".json", ".csv", ".md"}


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


def _filetime_to_int(ft: _FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


class SystemDiagnostics:
    """
    Read-only hardware health and diagnostic collector for CPU, System RAM, NVIDIA GPU,
    top processes, and user-selected log files.
    Does not require administrator privileges or arbitrary shell execution.
    """

    def __init__(self) -> None:
        self._last_cpu_times: tuple[int, int, int] | None = None
        self._last_cpu_percent: float = 0.0
        # Prime the CPU counter once at startup
        self._read_cpu_times()

    def _read_cpu_times(self) -> tuple[int, int, int] | None:
        idle = _FILETIME()
        kernel = _FILETIME()
        user = _FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        )
        if not ok:
            return None
        return (_filetime_to_int(idle), _filetime_to_int(kernel), _filetime_to_int(user))

    def get_cpu_status(self) -> dict[str, Any]:
        """Calculate system-wide CPU utilization via Win32 GetSystemTimes (read-only)."""
        current = self._read_cpu_times()
        if not current:
            return {"available": False, "load_percent": None, "collector": "Win32 GetSystemTimes"}

        if self._last_cpu_times is None:
            time.sleep(0.05)
            second = self._read_cpu_times()
            if second:
                self._last_cpu_times = current
                current = second

        if self._last_cpu_times is not None:
            idle_diff = current[0] - self._last_cpu_times[0]
            kernel_diff = current[1] - self._last_cpu_times[1]
            user_diff = current[2] - self._last_cpu_times[2]
            total_diff = kernel_diff + user_diff
            if total_diff > 0:
                busy = max(0, total_diff - idle_diff)
                self._last_cpu_percent = round((busy / total_diff) * 100.0, 1)
        self._last_cpu_times = current

        return {
            "available": True,
            "name": _cpu_name(),
            "load_percent": self._last_cpu_percent,
            "collector": "Win32 kernel32.GetSystemTimes (read-only)",
        }

    def get_ram_status(self) -> dict[str, Any]:
        """Read physical memory usage via Win32 GlobalMemoryStatusEx (read-only)."""
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        if not ok:
            return {"available": False, "collector": "Win32 GlobalMemoryStatusEx"}

        total_gb = round(stat.ullTotalPhys / (1024**3), 2)
        avail_gb = round(stat.ullAvailPhys / (1024**3), 2)
        used_gb = round(total_gb - avail_gb, 2)
        return {
            "available": True,
            "total_gb": total_gb,
            "used_gb": used_gb,
            "available_gb": avail_gb,
            "load_percent": float(stat.dwMemoryLoad),
            "collector": "Win32 kernel32.GlobalMemoryStatusEx (read-only)",
        }

    def get_gpu_status(self) -> dict[str, Any]:
        """Read NVIDIA GPU utilization and VRAM via read-only `nvidia-smi` query."""
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.free,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
                creationflags=creationflags,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return {
                    "available": False,
                    "error": res.stderr.strip() or "nvidia-smi returned no output",
                    "collector": "nvidia-smi --query-gpu (read-only)",
                }
            line = res.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                return {"available": False, "collector": "nvidia-smi --query-gpu (read-only)"}

            name = parts[0]
            gpu_util = float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else 0.0
            mem_used = float(parts[2]) if parts[2].replace(".", "", 1).isdigit() else 0.0
            mem_free = float(parts[3]) if parts[3].replace(".", "", 1).isdigit() else 0.0
            mem_total = float(parts[4]) if parts[4].replace(".", "", 1).isdigit() else 1.0
            temp_c = float(parts[5]) if parts[5].replace(".", "", 1).isdigit() else None

            return {
                "available": True,
                "name": name,
                "load_percent": gpu_util,
                "vram_used_mib": int(mem_used),
                "vram_free_mib": int(mem_free),
                "vram_total_mib": int(mem_total),
                "vram_percent": round((mem_used / mem_total) * 100.0, 1) if mem_total > 0 else 0.0,
                "temperature_c": temp_c,
                "collector": "nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.free,memory.total,temperature.gpu (read-only)",
            }
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
                "collector": "nvidia-smi --query-gpu (read-only)",
            }

    def get_health_snapshot(self) -> dict[str, Any]:
        """Return a combined read-only snapshot of CPU, RAM, and GPU health."""
        return {
            "cpu": self.get_cpu_status(),
            "ram": self.get_ram_status(),
            "gpu": self.get_gpu_status(),
        }

    def get_top_processes(self, limit: int = 10) -> dict[str, Any]:
        """
        Return a read-only snapshot of the top running processes sorted by WorkingSet RAM (MB).
        Never modifies, suspends, or terminates processes.
        """
        safe_limit = max(1, min(int(limit), 25))
        ps_script = (
            f"Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First {safe_limit} "
            "@{N='name';E={$_.ProcessName}}, "
            "@{N='pid';E={$_.Id}}, "
            "@{N='memory_mb';E={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, "
            "@{N='cpu_seconds';E={if ($_.CPU -ne $null) {[math]::Round($_.CPU, 1)} else {0.0}}} | "
            "ConvertTo-Json -Compress"
        )
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
                creationflags=creationflags,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return {
                    "ok": False,
                    "processes": [],
                    "error": res.stderr.strip() or "Failed to query process snapshot.",
                    "collector": "PowerShell Get-Process (read-only snapshot)",
                }
            parsed = json.loads(res.stdout.strip())
            processes = parsed if isinstance(parsed, list) else [parsed]
            return {
                "ok": True,
                "count": len(processes),
                "processes": processes,
                "collector": "PowerShell Get-Process | Sort-Object WorkingSet64 -Descending (read-only)",
            }
        except Exception as exc:
            return {
                "ok": False,
                "processes": [],
                "error": str(exc),
                "collector": "PowerShell Get-Process (read-only snapshot)",
            }

    def read_log_file_tail(
        self, file_path: str, max_lines: int = 120, max_bytes: int = 16384
    ) -> dict[str, Any]:
        """
        Safely read the bounded tail of an explicitly user-selected text/log file.
        Fails explicitly if the path is missing, is a directory, or has an unsupported extension.
        """
        raw_path = (file_path or "").strip().strip('"').strip("'")
        if not raw_path:
            return {
                "ok": False,
                "error": "No log file path was provided.",
                "collector": "Bounded Local Log File Reader (read-only)",
            }

        target = Path(raw_path)
        try:
            resolved = target.resolve()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Invalid file path '{raw_path}': {exc}",
                "collector": "Bounded Local Log File Reader (read-only)",
            }

        if not resolved.exists():
            return {
                "ok": False,
                "error": f"File does not exist: {resolved}",
                "collector": "Bounded Local Log File Reader (read-only)",
            }
        if not resolved.is_file():
            return {
                "ok": False,
                "error": f"Path is not a regular file: {resolved}",
                "collector": "Bounded Local Log File Reader (read-only)",
            }

        ext = resolved.suffix.lower()
        if ext not in ALLOWED_LOG_EXTENSIONS:
            return {
                "ok": False,
                "error": (
                    f"Extension '{ext or '(none)'}' is not in the allowed read-only log/text list "
                    f"({', '.join(sorted(ALLOWED_LOG_EXTENSIONS))})."
                ),
                "collector": "Bounded Local Log File Reader (read-only)",
            }

        try:
            total_size = resolved.stat().st_size
            safe_bytes = max(1024, min(int(max_bytes), 65536))
            safe_lines = max(10, min(int(max_lines), 500))

            with resolved.open("rb") as f:
                if total_size > safe_bytes:
                    f.seek(total_size - safe_bytes)
                chunk = f.read(safe_bytes)

            text = chunk.decode("utf-8", errors="replace")
            all_lines = text.splitlines()
            tail_lines = all_lines[-safe_lines:]
            truncated = (total_size > safe_bytes) or (len(all_lines) > safe_lines)

            return {
                "ok": True,
                "file_name": resolved.name,
                "resolved_path": str(resolved),
                "total_size_bytes": total_size,
                "lines_returned": len(tail_lines),
                "truncated": truncated,
                "content": "\n".join(tail_lines),
                "collector": f"Bounded Local Log File Reader (last <= {safe_lines} lines / {safe_bytes} bytes, read-only)",
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Could not read file '{resolved}': {exc}",
                "collector": "Bounded Local Log File Reader (read-only)",
            }

    def get_recent_windows_events(self, max_events: int = 12) -> dict[str, Any]:
        """
        Opt-in read-only collector for recent Warning/Error events in Windows Application/System logs.
        Only called when explicitly requested by the user.
        """
        safe_max = max(1, min(int(max_events), 25))
        ps_script = (
            f"Get-WinEvent -FilterHashtable @{{LogName='Application','System'; Level=1,2,3}} "
            f"-MaxEvents {safe_max} -ErrorAction SilentlyContinue | "
            "Select-Object @{N='time';E={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}}, "
            "@{N='log';E={$_.LogName}}, "
            "@{N='level';E={$_.LevelDisplayName}}, "
            "@{N='provider';E={$_.ProviderName}}, "
            "@{N='id';E={$_.Id}}, "
            "@{N='message';E={if ($_.Message) { ($_.Message -replace '\\s+',' ').Substring(0, [math]::Min(240, ($_.Message -replace '\\s+',' ').Length)) } else { '' }}} | "
            "ConvertTo-Json -Compress"
        )
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
                creationflags=creationflags,
            )
            raw = res.stdout.strip()
            if not raw:
                return {
                    "ok": True,
                    "count": 0,
                    "events": [],
                    "collector": "PowerShell Get-WinEvent Application/System Warning+Error (read-only)",
                }
            parsed = json.loads(raw)
            events = parsed if isinstance(parsed, list) else [parsed]
            return {
                "ok": True,
                "count": len(events),
                "events": events,
                "collector": f"PowerShell Get-WinEvent Application/System Level<=3 MaxEvents={safe_max} (read-only)",
            }
        except Exception as exc:
            return {
                "ok": False,
                "events": [],
                "error": str(exc),
                "collector": "PowerShell Get-WinEvent Application/System (read-only)",
            }

    def ensure_sample_diagnostic_log(self) -> dict[str, Any]:
        """Create a sample diagnostic log inside loki/data/sample_system.log for testing."""
        ensure_data_dir()
        sample_path = DATA_DIR / "sample_system.log"
        sample_lines = [
            "2026-11-15 13:55:01 [INFO] [SystemBoot] Workstation startup complete. Usable RAM: 15.23 GB.",
            "2026-11-15 13:56:12 [INFO] [GPUDriver] NVIDIA GeForce RTX 5050 Laptop GPU initialized (8151 MiB VRAM, Driver 610.71).",
            "2026-11-15 13:58:44 [WARN] [BackgroundIndexer] SearchIndexer.exe high disk read latency (412 ms) on C:\\Users\\User\\AppData.",
            "2026-11-15 14:01:09 [ERROR] [AudioService] USB Audio Endpoint timeout after 3000ms (ErrorCode: 0x800705B4) — retrying connection.",
            "2026-11-15 14:02:15 [WARN] [MemoryGuard] Browser tab pool allocated 3,420 MB across 28 renderer processes.",
            "2026-11-15 14:04:30 [INFO] [OllamaDaemon] Listening on 127.0.0.1:11434 (v0.40.13). Model llama3:latest ready.",
            "2026-11-15 14:05:00 [ERROR] [UpdaterTask] ThirdPartyHelper.exe failed to connect to update server (timeout after 5000ms); scheduled retry in 60s.",
        ]
        sample_path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "path": str(sample_path.resolve()),
            "lines": len(sample_lines),
        }


system_diagnostics = SystemDiagnostics()
