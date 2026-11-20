"""Local tools: system check, file tools, reminders and game-project checks. All run on this PC only.

- System (read-only): what uses RAM / CPU / GPU, free disk space, apps that start with Windows.
- Files: largest files and duplicates in a folder (read-only); "organise" makes a plan that moves files into
  type folders, shown first and only applied after the user approves it, with an undo log.
- Reminders: stored in data/reminders.json; a background loop shows a Windows notification when one is due.
- Game projects: Godot (project.godot) and Unity (Assets + ProjectSettings) health checks.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ensure_data_dir

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
SKIP_DIRS = {"$recycle.bin", "system volume information", "windows", "program files", "program files (x86)",
             "programdata", "appdata", "node_modules", ".git", "__pycache__", ".venv", "venv", "library", "temp",
             ".godot", ".import", "obj"}
MAX_SCAN_FILES = 150_000


class ToolError(Exception):
    pass


def _ps_json(script: str, timeout: float = 15.0) -> Any:
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    out = (res.stdout or "").strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# System (read-only)
# ---------------------------------------------------------------------------
def system_report() -> dict[str, Any]:
    """RAM/CPU hogs, GPU users, disk space and startup apps."""
    procs = _ps_json(
        "Get-Process | Group-Object ProcessName | ForEach-Object { [pscustomobject]@{ name = $_.Name; count = $_.Count; "
        "memory_mb = [math]::Round(($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB); "
        "cpu_s = [math]::Round(($_.Group | Measure-Object CPU -Sum).Sum, 0) } } | "
        "Sort-Object memory_mb -Descending | Select-Object -First 12 | ConvertTo-Json -Compress")
    gpu: list[dict[str, Any]] = []
    try:
        res = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=6, creationflags=CREATE_NO_WINDOW)
        for line in (res.stdout or "").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 3 and parts[2].isdigit():
                gpu.append({"pid": parts[0], "name": Path(parts[1]).name, "vram_mb": int(parts[2])})
        res = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=6, creationflags=CREATE_NO_WINDOW)
        g = [p.strip() for p in (res.stdout or "").splitlines()[0].split(",")] if res.stdout.strip() else []
        gpu_summary = ({"name": g[0], "used_mb": int(g[1]), "total_mb": int(g[2]), "util_pct": int(g[3]), "temp_c": int(g[4])}
                       if len(g) == 5 else None)
    except (OSError, subprocess.SubprocessError, ValueError):
        gpu_summary = None
    disks = []
    for letter in "CDEFGHIJ":
        root = f"{letter}:\\"
        if os.path.exists(root):
            try:
                u = shutil.disk_usage(root)
                disks.append({"drive": f"{letter}:", "free_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1),
                              "used_pct": round(100 * u.used / u.total)})
            except OSError:
                pass
    startup = _ps_json(
        "$r = @(); foreach ($k in 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run','HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run') { "
        "if (Test-Path $k) { $p = Get-ItemProperty $k; $p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | "
        "ForEach-Object { $r += [pscustomobject]@{ name = $_.Name; where = $(if ($k -like 'HKCU*') {'You'} else {'All users'}) } } } }; "
        "foreach ($f in \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\") { if (Test-Path $f) { "
        "Get-ChildItem $f -File | ForEach-Object { $r += [pscustomobject]@{ name = $_.BaseName; where = 'Startup folder' } } } }; "
        "$r | ConvertTo-Json -Compress")

    class _MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                    ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
    ms = _MS()
    ms.dwLength = ctypes.sizeof(_MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return {"ram": {"total_gb": round(ms.ullTotalPhys / 1e9, 1), "free_gb": round(ms.ullAvailPhys / 1e9, 1),
                    "used_pct": int(ms.dwMemoryLoad)},
            "top_memory": procs, "gpu": gpu_summary, "gpu_apps": sorted(gpu, key=lambda x: -x["vram_mb"])[:8],
            "disks": disks, "startup_apps": startup, "time": datetime.now().isoformat(timespec="seconds")}


def system_report_text(r: dict[str, Any]) -> str:
    lines = [f"RAM: {r['ram']['used_pct']}% used, {r['ram']['free_gb']} GB free of {r['ram']['total_gb']} GB."]
    lines.append("Top memory users: " + ", ".join(
        f"{p['name']}{' x' + str(p['count']) if p.get('count', 1) > 1 else ''} {p['memory_mb']} MB" for p in r["top_memory"][:8]))
    if r.get("gpu"):
        g = r["gpu"]
        lines.append(f"GPU {g['name']}: {g['used_mb']}/{g['total_mb']} MB VRAM, {g['util_pct']}% busy, {g['temp_c']} C.")
    if r.get("gpu_apps"):
        lines.append("GPU memory users: " + ", ".join(f"{a['name']} {a['vram_mb']} MB" for a in r["gpu_apps"]))
    lines.append("Disks: " + ", ".join(f"{d['drive']} {d['free_gb']} GB free of {d['total_gb']} GB" for d in r["disks"]))
    if r.get("startup_apps"):
        lines.append("Starts with Windows: " + ", ".join(f"{s['name']} ({s['where']})" for s in r["startup_apps"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def check_folder(raw: str) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(str(raw or "").strip().strip('"')))).resolve()
    if not p.is_dir():
        raise ToolError(f"Folder not found: {raw}")
    low = str(p).lower().rstrip("\\")
    blocked = ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "c:\\programdata"]
    if any(low == b or low.startswith(b + "\\") for b in blocked) or len(p.parts) < 2 and low.startswith("c:"):
        raise ToolError("Loki does not scan or reorganise Windows or program folders. Pick one of your own folders.")
    return p


def _walk(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            count += 1
            if count > MAX_SCAN_FILES:
                return
            yield Path(dirpath) / name


def largest_files(raw: str, limit: int = 25) -> dict[str, Any]:
    root = check_folder(raw)
    items, total, n = [], 0, 0
    for p in _walk(root):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        n += 1
        total += size
        items.append((size, p))
    items.sort(key=lambda x: -x[0])
    return {"folder": str(root), "files_scanned": n, "total": _human(total),
            "files": [{"path": str(p), "size": _human(s), "bytes": s} for s, p in items[:limit]]}


def duplicate_files(raw: str, min_bytes: int = 100_000) -> dict[str, Any]:
    root = check_folder(raw)
    by_size: dict[int, list[Path]] = {}
    for p in _walk(root):
        try:
            s = p.stat().st_size
        except OSError:
            continue
        if s >= min_bytes:
            by_size.setdefault(s, []).append(p)
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[Path]] = {}
        for p in paths[:20]:
            try:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
                by_hash.setdefault(h.hexdigest(), []).append(p)
            except OSError:
                continue
        for same in by_hash.values():
            if len(same) > 1:
                groups.append({"size": _human(size), "wasted": _human(size * (len(same) - 1)), "bytes": size * (len(same) - 1),
                               "paths": [str(x) for x in same]})
    groups.sort(key=lambda g: -g["bytes"])
    return {"folder": str(root), "groups": groups[:40], "wasted_total": _human(sum(g["bytes"] for g in groups))}


TYPE_FOLDERS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".ico", ".tif", ".tiff", ".psd"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".msix", ".appx"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".cs", ".cpp", ".c", ".h", ".java", ".gd", ".lua", ".ps1", ".bat", ".sh"},
}
_PLANS: dict[str, dict[str, Any]] = {}
MOVE_LOG = DATA_DIR / "organise_log.json"


def organise_plan(raw: str) -> dict[str, Any]:
    """Plan (not do) moving the loose files at the top of a folder into type folders."""
    root = check_folder(raw)
    moves = []
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in (".lnk", ".ini", ".url"):
            continue
        folder = next((name for name, exts in TYPE_FOLDERS.items() if p.suffix.lower() in exts), None)
        if folder:
            moves.append({"from": str(p), "to": str(root / folder / p.name), "folder": folder})
    plan_id = uuid.uuid4().hex[:12]
    _PLANS[plan_id] = {"root": str(root), "moves": moves, "created": time.time()}
    summary: dict[str, int] = {}
    for m in moves:
        summary[m["folder"]] = summary.get(m["folder"], 0) + 1
    return {"plan_id": plan_id, "folder": str(root), "moves": moves[:300], "count": len(moves), "summary": summary}


def apply_plan(plan_id: str) -> dict[str, Any]:
    plan = _PLANS.pop(plan_id, None)
    if not plan or time.time() - plan["created"] > 1800:
        raise ToolError("That plan has expired. Make a new one.")
    done, skipped = [], []
    for m in plan["moves"]:
        src, dst = Path(m["from"]), Path(m["to"])
        if not src.is_file() or dst.exists():
            skipped.append(m["from"])
            continue
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        done.append({"from": str(src), "to": str(dst)})
    ensure_data_dir()
    log = json.loads(MOVE_LOG.read_text(encoding="utf-8")) if MOVE_LOG.exists() else []
    batch = {"id": uuid.uuid4().hex[:12], "time": datetime.now().isoformat(timespec="seconds"), "moves": done}
    log.insert(0, batch)
    MOVE_LOG.write_text(json.dumps(log[:20], indent=1), encoding="utf-8")
    return {"moved": len(done), "skipped": len(skipped), "undo_id": batch["id"]}


def undo_organise(batch_id: str) -> dict[str, Any]:
    log = json.loads(MOVE_LOG.read_text(encoding="utf-8")) if MOVE_LOG.exists() else []
    batch = next((b for b in log if b["id"] == batch_id), None)
    if not batch:
        raise ToolError("Nothing to undo for that.")
    back = 0
    for m in reversed(batch["moves"]):
        src, dst = Path(m["to"]), Path(m["from"])
        if src.is_file() and not dst.exists():
            shutil.move(str(src), str(dst))
            back += 1
            try:
                src.parent.rmdir()  # only removes the type folder if it is now empty
            except OSError:
                pass
    log = [b for b in log if b["id"] != batch_id]
    MOVE_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    return {"restored": back}


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
REMINDERS_FILE = DATA_DIR / "reminders.json"
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_REMIND = re.compile(r"^\s*(?:please\s+|hey loki,?\s+)?(?:remind me|set (?:a )?reminder|add (?:a )?reminder)\b\s*(?:to\s+)?(.*)$", re.I | re.S)


def _load_reminders() -> list[dict[str, Any]]:
    try:
        data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_reminders(items: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    REMINDERS_FILE.write_text(json.dumps(items, indent=1), encoding="utf-8")


def parse_when(text: str, now: datetime | None = None) -> tuple[datetime | None, str]:
    """Find a time in plain English. Returns (when, text with the time words removed)."""
    now = now or datetime.now()
    t = " " + text.strip() + " "
    when: datetime | None = None

    def cut(m: re.Match) -> None:
        nonlocal t
        t = t[:m.start()] + " " + t[m.end():]

    m = re.search(r"\bin\s+(\d+|an?|half an)\s*(min(?:ute)?s?|hours?|hrs?|days?|weeks?)\b", t, re.I)
    if m:
        n = {"a": 1, "an": 1, "half an": 0.5}.get(m.group(1).lower(), None)
        n = float(m.group(1)) if n is None else n
        unit = m.group(2).lower()
        delta = (timedelta(minutes=n) if unit.startswith("min") else timedelta(hours=n) if unit.startswith(("hour", "hr"))
                 else timedelta(days=n) if unit.startswith("day") else timedelta(weeks=n))
        cut(m)
        return now + delta, re.sub(r"\s+", " ", t).strip()

    day: datetime | None = None
    weekday_given = False
    m = re.search(r"\b(today|tonight|tomorrow|tmrw|next week|(?:on\s+|next\s+|this\s+)?(" + "|".join(_DAYS) + r"))\b", t, re.I)
    if m:
        w = m.group(1).lower()
        if w in ("today", "tonight"):
            day = now
        elif w in ("tomorrow", "tmrw"):
            day = now + timedelta(days=1)
        elif w == "next week":
            day = now + timedelta(days=7)
        else:
            target = _DAYS.index(m.group(2).lower())
            ahead = (target - now.weekday()) % 7  # 0 = today if the time is still ahead
            weekday_given = True
            day = now + timedelta(days=ahead)
        cut(m)
    else:
        m = re.search(r"\bon\s+(\d{1,2})[/.-](\d{1,2})\b", t)
        if m:
            try:
                day = now.replace(month=int(m.group(2)), day=int(m.group(1)))
                if day.date() < now.date():
                    day = day.replace(year=now.year + 1)
                cut(m)
            except ValueError:
                day = None
    hour = minute = None
    m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", t, re.I) or \
        re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b(?!\s*(?:%|percent))", t, re.I)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ap = (m.group(3) or "").lower().replace(".", "") if m.lastindex and m.lastindex >= 3 else ""
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        elif not ap and 1 <= hour <= 7:
            hour += 12  # "at 5" means 5 pm
        cut(m)
    elif re.search(r"\b(morning)\b", t, re.I):
        hour, minute = 9, 0
    elif re.search(r"\b(afternoon)\b", t, re.I):
        hour, minute = 14, 0
    elif re.search(r"\b(evening|tonight)\b", t, re.I) or (day is not None and m is None and "tonight" in text.lower()):
        hour, minute = 19, 0
    t = re.sub(r"\b(in the )?(morning|afternoon|evening)\b", " ", t, flags=re.I)
    if hour is not None and hour < 24 and minute < 60:
        base = day or now
        when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if when <= now and day is None:
            when += timedelta(days=1)
        elif when <= now and weekday_given:
            when += timedelta(days=7)
    elif day is not None:
        when = day.replace(hour=9, minute=0, second=0, microsecond=0)
    return when, re.sub(r"\s+", " ", t).strip()


def is_reminder_request(text: str) -> bool:
    return bool(_REMIND.match(text or ""))


def add_reminder(text: str, when: datetime | None = None) -> dict[str, Any]:
    raw = text
    m = _REMIND.match(text or "")
    if m:
        raw = m.group(1)
    if when is None:
        when, raw = parse_when(raw)
    what = re.sub(r"^((this|to|that|about)\s+)+", "", raw.strip(" .,!"), flags=re.I) or "Reminder"
    if when is None:
        raise ToolError("When should I remind you? Say a time, e.g. \"remind me tomorrow at 9 to call Sam\" or \"in 20 minutes\".")
    item = {"id": uuid.uuid4().hex[:10], "text": what[:300], "due": when.isoformat(timespec="minutes"),
            "created": datetime.now().isoformat(timespec="seconds"), "done": False, "notified": False}
    items = _load_reminders()
    items.append(item)
    items.sort(key=lambda x: x["due"])
    _save_reminders(items)
    return item


def list_reminders(include_done: bool = False) -> list[dict[str, Any]]:
    return [r for r in _load_reminders() if include_done or not r.get("done")]


def update_reminder(rid: str, done: bool | None = None, delete: bool = False) -> bool:
    items = _load_reminders()
    found = False
    for r in list(items):
        if r["id"] == rid:
            found = True
            if delete:
                items.remove(r)
            elif done is not None:
                r["done"] = bool(done)
    _save_reminders(items)
    return found


def describe_when(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    now = datetime.now()
    day = ("today" if d.date() == now.date() else "tomorrow" if d.date() == (now + timedelta(days=1)).date()
           else d.strftime("%A %d %B") if (d - now).days < 6 else d.strftime("%d %B %Y"))
    return f"{day} at {d.strftime('%H:%M')}"


def _notify(title: str, body: str) -> None:
    """Windows toast notification (no extra software): uses PowerShell's built-in WinRT access."""
    t = title.replace("'", "''")[:80]
    b = body.replace("'", "''")[:240]
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
        "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        f"$t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('{t}')) > $null; "
        f"$t.Item(1).AppendChild($x.CreateTextNode('{b}')) > $null; "
        "$n = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Loki.LocalAI').Show($n)")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    except OSError:
        pass


DUE_EVENTS: list[dict[str, Any]] = []  # picked up by the open Loki window for an in-app alert


def check_due() -> list[dict[str, Any]]:
    items = _load_reminders()
    now = datetime.now()
    fired = []
    for r in items:
        if not r.get("done") and not r.get("notified") and datetime.fromisoformat(r["due"]) <= now:
            r["notified"] = True
            fired.append(r)
            _notify("Loki reminder", r["text"])
    if fired:
        _save_reminders(items)
        DUE_EVENTS.extend(fired)
        del DUE_EVENTS[:-20]
    return fired


async def reminder_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(check_due)
        except Exception:
            pass
        await asyncio.sleep(20)


# ---------------------------------------------------------------------------
# Game projects (Godot / Unity)
# ---------------------------------------------------------------------------
def detect_engine(root: Path) -> str | None:
    if (root / "project.godot").is_file():
        return "godot"
    if (root / "Assets").is_dir() and (root / "ProjectSettings").is_dir():
        return "unity"
    return None


def _issue(level: str, where: str, what: str, fix: str) -> dict[str, str]:
    return {"level": level, "where": where, "what": what, "fix": fix}


def check_godot(root: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    proj = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    name = (re.search(r'config/name="([^"]*)"', proj) or [None, root.name])[1]
    version = (re.search(r'config/features=PackedStringArray\("([\d.]+)"', proj) or [None, "?"])[1]
    main = re.search(r'run/main_scene="res://([^"]+)"', proj)
    if not main:
        issues.append(_issue("error", "project.godot", "No main scene is set, so the game cannot start with F5.",
                             "Project > Project Settings > Application > Run > Main Scene."))
    elif not (root / main.group(1)).is_file():
        issues.append(_issue("error", "project.godot", f"The main scene {main.group(1)} does not exist.", "Pick an existing scene as Main Scene."))
    scripts, scenes, referenced = [], [], set()
    for p in _walk(root):
        ext = p.suffix.lower()
        rel = p.relative_to(root).as_posix()
        if ext == ".gd":
            scripts.append(rel)
        elif ext in (".tscn", ".tres"):
            scenes.append(rel)
        elif ext in (".png", ".jpg", ".jpeg", ".wav", ".ogg", ".mp3") and p.stat().st_size > 8_000_000:
            issues.append(_issue("warn", rel, f"Large asset ({_human(p.stat().st_size)}).", "Compress or downscale it to keep exports small."))
    for rel in scenes:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for ref in re.findall(r'path="res://([^"]+)"', text):
            referenced.add(ref)
            if not (root / ref).exists():
                issues.append(_issue("error", rel, f"References res://{ref}, which does not exist.", "Restore the file or fix the path in the scene."))
    for rel in scripts:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        indents = {("tab" if ln.startswith("\t") else "space") for ln in lines if ln[:1] in ("\t", " ") and ln.strip()}
        if len(indents) > 1:
            issues.append(_issue("error", rel, "Mixes tabs and spaces for indentation (Godot will refuse to parse it).",
                                 "Use tabs everywhere (Editor > Convert Indent To Tabs)."))
        for i, ln in enumerate(lines, 1):
            if re.search(r"func _(physics_)?process\(", ln):
                body = "\n".join(lines[i:i + 25])
                if re.search(r'get_node\(|\$"?[A-Za-z]|find_child\(|load\(', body):
                    issues.append(_issue("warn", f"{rel}:{i}", "Looks up nodes or loads resources every frame inside _process.",
                                         "Cache it once with @onready var x = $Node, or preload() the resource."))
                    break
        if rel not in referenced and not re.search(r"^class_name\s", text, re.M) and "autoload" not in proj.lower() + rel.lower():
            if f'"*res://{rel}"' not in proj:
                issues.append(_issue("info", rel, "Not used by any scene and has no class_name (maybe unused).", "Delete it or attach it to a node."))
    return {"engine": "Godot", "name": name, "engine_version": version, "scripts": len(scripts), "scenes": len(scenes),
            "issues": issues[:60]}


def check_unity(root: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ver_file = root / "ProjectSettings" / "ProjectVersion.txt"
    version = (re.search(r"m_EditorVersion:\s*(\S+)", ver_file.read_text(encoding="utf-8", errors="replace")) or [None, "?"])[1] \
        if ver_file.is_file() else "?"
    scripts = 0
    assets = root / "Assets"
    for p in _walk(assets):
        rel = p.relative_to(root).as_posix()
        if p.suffix.lower() != ".meta" and not Path(str(p) + ".meta").exists():
            issues.append(_issue("warn", rel, "Has no .meta file (references to it can break).", "Open the project in Unity so it creates one, and commit .meta files."))
        if p.suffix.lower() == ".cs":
            scripts += 1
            text = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"class\s+(\w+)\s*:\s*(MonoBehaviour|ScriptableObject)", text)
            if m and m.group(1) != p.stem:
                issues.append(_issue("error", rel, f"Class {m.group(1)} does not match the file name {p.stem}.cs, so Unity cannot attach it.",
                                     f"Rename the class or the file so both are {p.stem}."))
            upd = re.search(r"void\s+(Fixed)?Update\s*\(\s*\)\s*\{(.{0,1500}?)\n\s*\}", text, re.S)
            if upd and re.search(r"GetComponent<|GameObject\.Find|FindObjectOfType|Camera\.main", upd.group(2)):
                issues.append(_issue("warn", rel, "Calls GetComponent / Find / Camera.main every frame in Update.",
                                     "Cache the reference in Awake() or Start()."))
            if re.search(r"\bpublic\s+\w+\s+\w+\s*;", text) and "SerializeField" not in text:
                issues.append(_issue("info", rel, "Uses public fields for Inspector values.", "Prefer [SerializeField] private fields."))
        elif p.suffix.lower() in (".png", ".psd", ".tga", ".wav", ".fbx") and p.stat().st_size > 20_000_000:
            issues.append(_issue("warn", rel, f"Large asset ({_human(p.stat().st_size)}).", "Check its import settings (max size, compression)."))
    if (assets / "Resources").is_dir():
        size = sum(p.stat().st_size for p in _walk(assets / "Resources"))
        if size > 200_000_000:
            issues.append(_issue("warn", "Assets/Resources", f"Resources folder is {_human(size)}; everything in it ships in the build.",
                                 "Move rarely used assets out, or use Addressables."))
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: order[i["level"]])
    return {"engine": "Unity", "name": root.name, "engine_version": version, "scripts": scripts, "issues": issues[:60]}


def check_game_project(raw: str) -> dict[str, Any]:
    root = check_folder(raw)
    engine = detect_engine(root)
    if engine is None:
        raise ToolError("This folder is not a Godot project (no project.godot) or a Unity project (no Assets + ProjectSettings).")
    report = check_godot(root) if engine == "godot" else check_unity(root)
    report["folder"] = str(root)
    report["counts"] = {lvl: sum(1 for i in report["issues"] if i["level"] == lvl) for lvl in ("error", "warn", "info")}
    return report


def game_report_text(r: dict[str, Any]) -> str:
    lines = [f"{r['engine']} project {r['name']} (engine {r['engine_version']}): {r.get('scripts', 0)} scripts"
             + (f", {r['scenes']} scenes" if "scenes" in r else "") + "."]
    for i in r["issues"][:30]:
        lines.append(f"- [{i['level']}] {i['where']}: {i['what']} Fix: {i['fix']}")
    if not r["issues"]:
        lines.append("No problems found.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat intents: which tool (if any) a chat message asks for
# ---------------------------------------------------------------------------
_LIST_REMINDERS = re.compile(r"\b(what|show|list|any|my|upcoming)\b.{0,30}\b(reminders?|calendar|schedule|agenda)\b", re.I)
_SYSTEM = re.compile(
    r"what('?s| is| are)\s+(using|eating|hogging|taking)\s+(up\s+)?(all\s+)?(my\s+)?(ram|memory|cpu|gpu|vram|disk)|"
    r"why\s+is\s+my\s+(pc|computer|laptop|system)\s+(so\s+)?(slow|laggy|lagging)|"
    r"(how much|check)\s+(free\s+)?(disk|storage|drive)\s+space|disk space|free space on|"
    r"startup\s+(apps|programs)|starts?\s+with\s+windows|system\s+check|check\s+my\s+(pc|system|computer)", re.I)
_GAME = re.compile(r"\b(check|audit|review|scan|analy[sz]e|inspect)\b.{0,40}\b(godot|unity|game)\b.{0,20}\b(project|game|folder)\b", re.I)
_LARGEST = re.compile(r"\b(largest|biggest|big|huge)\s+files?\b|what('?s| is)\s+taking\s+(up\s+)?space\s+in", re.I)
_DUPES = re.compile(r"\bduplicate(d)?\s+(files|photos|images|pictures)?|\bdupes\b", re.I)
_ORGANISE = re.compile(r"\b(organi[sz]e|tidy|clean\s*up|sort)\b.{0,20}\b(my\s+)?(downloads|desktop|documents|folder|files)\b", re.I)
_PATH = re.compile(r"\"([A-Za-z]:[\\/][^\"]+)\"|'([A-Za-z]:[\\/][^']+)'|([A-Za-z]:[\\/][^\s\"',;?]*)")
_KNOWN = {"downloads": "Downloads", "desktop": "Desktop", "documents": "Documents", "pictures": "Pictures",
          "photos": "Pictures", "videos": "Videos", "music": "Music"}


def folder_in_text(text: str) -> str | None:
    m = _PATH.search(text or "")
    if m:
        return (m.group(1) or m.group(2) or m.group(3)).rstrip("\\/.") or None
    for word, sub in _KNOWN.items():
        if re.search(rf"\b(my\s+)?{word}\b", text or "", re.I):
            p = Path.home() / sub
            return str(p) if p.is_dir() else None
    return None


def detect_intent(text: str, project_root: str | None = None) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t or len(t) > 600:
        return None
    if is_reminder_request(t):
        return {"tool": "reminder_add"}
    if _LIST_REMINDERS.search(t) and not re.search(r"\b(code|function|app|script)\b", t, re.I):
        return {"tool": "reminder_list"}
    if _GAME.search(t):
        return {"tool": "game_check", "folder": folder_in_text(t) or project_root}
    if _SYSTEM.search(t):
        return {"tool": "system"}
    if _ORGANISE.search(t):
        return {"tool": "organise", "folder": folder_in_text(t)}
    if _DUPES.search(t):
        return {"tool": "duplicates", "folder": folder_in_text(t)}
    if _LARGEST.search(t):
        return {"tool": "largest", "folder": folder_in_text(t)}
    return None
