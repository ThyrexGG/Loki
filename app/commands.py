"""PC help: PowerShell commands that Loki proposes and the user approves (ADR-014).

Flow: Loki writes a ```powershell block -> user clicks Run -> /api/commands/review rates the risk and
returns a one-time token -> user confirms -> /api/commands/run executes it (as the user, never elevated,
60 s limit, output capped) and logs it to data/command_log.json.

Risk levels:
- "read"    : looks read-only (Get-*, Test-*, ipconfig, ping, ...). Still requires a click.
- "change"  : changes something (delete, stop, install, set, registry, network config). Red "Run anyway".
- "blocked" : destructive or high-abuse patterns. Loki refuses to run them; the user can copy and run
              them manually if they are sure.
- "admin"   : needs an elevated prompt (sfc, DISM, ...). Loki cannot elevate, so it explains how to run it.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ensure_data_dir

LOG_FILE = DATA_DIR / "command_log.json"
TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 20_000
MAX_COMMAND_CHARS = 4_000
_SECRET = secrets.token_bytes(32)  # per server process; tokens die on restart

_BLOCKED = [
    (r"\bformat(-volume)?\b\s+[a-z]:|\bformat-volume\b|\bclear-disk\b|\binitialize-disk\b|\bdiskpart\b", "formats or wipes a disk"),
    (r"\bbcdedit\b|\bbootrec\b", "changes how Windows boots"),
    (r"\bcipher\b\s+/w", "wipes free disk space"),
    (r"\bvssadmin\b.*\bdelete\b|\bwmic\b.*shadowcopy.*delete", "deletes System Restore / shadow copies"),
    (r"(remove-item|\brm\b|\bdel\b|\brd\b|\brmdir\b|\berase\b)[^\n|;]*\b[a-z]:\\(windows|program files|programdata|users\b(?!\\[^\\\s]+\\))",
     "deletes files in a system folder"),
    (r"(remove-item|\brm\b|\bdel\b|\brd\b|\brmdir\b)[^\n|;]*\s[\"']?[a-z]:\\?[\"']?(\s|$)", "deletes a whole drive"),
    (r"set-mppreference[^\n]*-disable|add-mppreference[^\n]*-exclusion|\bstop-service\b[^\n]*windefend", "turns off or weakens Windows Defender"),
    (r"(invoke-webrequest|\biwr\b|invoke-restmethod|\birm\b|curl|wget|downloadstring|downloadfile)[^\n]*\|\s*(invoke-expression|iex)\b|\biex\b\s*\(\s*(new-object|iwr|irm|invoke-)",
     "downloads code from the internet and runs it immediately"),
    (r"-encodedcommand\b|\s-enc\s|frombase64string[^\n]*(invoke-expression|iex)", "runs hidden (encoded) code"),
    (r"\bnet\s+user\b[^\n]*(/add|/delete)|\bnet\s+localgroup\s+administrators\b[^\n]*/add|new-localuser|add-localgroupmember", "creates users or grants admin rights"),
    (r"\breg(\.exe)?\s+delete\s+hklm|remove-item[^\n]*hklm:", "deletes system registry keys"),
    (r"mimikatz|sekurlsa|lsass|procdump[^\n]*lsass|\bsam\b.*\bsave\b", "touches stored passwords or credentials"),
    (r"set-executionpolicy[^\n]*(unrestricted|bypass)[^\n]*(localmachine|-force)", "lowers the system-wide script safety setting"),
    (r"\bshutdown\b[^\n]*/(s|r|p)\b|stop-computer|restart-computer", "shuts down or restarts the PC"),
]
_ADMIN = [
    (r"\bsfc\b\s*/scannow", "System File Checker"), (r"\bdism\b", "DISM"), (r"\bchkdsk\b", "Check Disk"),
    (r"\bnetsh\b\s+(winsock|int(erface)?\s+ip)\s+reset", "network stack reset"),
    (r"\b(stop|start|restart)-service\b|\bsc(\.exe)?\s+(stop|start|config|delete)\b|\bnet\s+(stop|start)\b", "service control"),
    (r"\breg(\.exe)?\s+add\s+hklm|set-itemproperty[^\n]*hklm:", "system registry change"),
]
_CHANGE = [
    (r"\b(remove|clear|stop|set|new|rename|move|copy|install|uninstall|update|disable|enable|reset|restart|register|unregister|add|start|suspend|resume|invoke|write|out|export|import|mount|dismount|publish|unpublish|grant|revoke|block|unblock|lock|unlock)-[a-z]+",
     "runs a command that changes something"),
    (r"(^|[\s;|(])(del|erase|rd|rmdir|rm|mv|move|copy|cp|ren|rename|mkdir|md)\s", "creates, moves or deletes files"),
    (r"\b(winget|choco|scoop|pip|npm|msiexec)\b\s+(install|uninstall|upgrade|remove|update)", "installs or removes software"),
    (r"\bnetsh\b|\broute\s+(add|delete|change)|\bipconfig\s+/(release|renew|flushdns)", "changes network settings"),
    (r"\breg(\.exe)?\s+(add|delete|import)|set-itemproperty|new-itemproperty|remove-itemproperty", "changes the registry"),
    (r"\btaskkill\b|\bkill\b", "ends running programs"),
    (r"(^|[^<])>{1,2}\s*[^\s&]", "writes output to a file"),
    (r"\bschtasks\b\s+/(create|delete|change)", "changes scheduled tasks"),
    (r"\bpowercfg\b\s+/(change|setactive|hibernate|delete)", "changes power settings"),
]
# Commands that read but match a "change" verb pattern by name only.
_READ_OK = re.compile(r"\b(out-string|out-host|write-output|write-host|test-[a-z]+|select-[a-z]+|sort-object|measure-object|format-[a-z]+|where-object|foreach-object)\b", re.I)


def assess(command: str) -> dict[str, Any]:
    cmd = (command or "").strip()
    low = cmd.lower()
    if not cmd:
        return {"level": "blocked", "reasons": ["The command is empty."], "admin": False}
    if len(cmd) > MAX_COMMAND_CHARS:
        return {"level": "blocked", "reasons": ["The command is too long to review safely."], "admin": False}
    blocked = [why for pat, why in _BLOCKED if re.search(pat, low)]
    if blocked:
        return {"level": "blocked", "reasons": sorted(set(blocked)), "admin": False}
    admin = [what for pat, what in _ADMIN if re.search(pat, low)]
    stripped = _READ_OK.sub(" ", low)
    change = [why for pat, why in _CHANGE if re.search(pat, stripped)]
    if admin:
        return {"level": "admin", "reasons": [f"Needs an administrator PowerShell ({', '.join(sorted(set(admin)))})."]
                + sorted(set(change)), "admin": True}
    if change:
        return {"level": "change", "reasons": sorted(set(change)), "admin": False}
    return {"level": "read", "reasons": ["Looks read-only: it only shows information."], "admin": False}


def _token(command: str) -> str:
    return hmac.new(_SECRET, command.encode("utf-8"), hashlib.sha256).hexdigest()


def review(command: str) -> dict[str, Any]:
    result = assess(command)
    result["token"] = _token(command) if result["level"] in ("read", "change") else None
    result["timeout_seconds"] = TIMEOUT_SECONDS
    return result


def _run_blocking(command: str, cwd: str, prelude: str = "") -> dict[str, Any]:
    # Merge errors into the output as readable text (captured stderr would otherwise be CLIXML), and
    # turn cmdlet errors into a non-zero exit code. `prelude` is trusted setup code from Loki itself
    # (the coding agent uses it to point `python` at the real interpreter).
    default_py = (
        "$__lokiPy = Join-Path $env:LOCALAPPDATA 'Python\\bin\\python.exe'\n"
        "if (Test-Path $__lokiPy) { function python { & $__lokiPy @args }; function python3 { & $__lokiPy @args }; "
        "function py { & $__lokiPy @args }; function pip { & $__lokiPy -m pip @args } }\n"
    )
    script = (
        "$ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;\n"
        + default_py + prelude +
        "$__lokiErr = $false; $global:LASTEXITCODE = 0\n"
        "& {\n" + command + "\n} 2>&1 | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) "
        "{ $__lokiErr = $true; 'ERROR: ' + $_.ToString() } else { $_ } } | Out-String -Width 220\n"
        "if ($LASTEXITCODE) { exit $LASTEXITCODE } elseif ($__lokiErr) { exit 1 } else { exit 0 }\n"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    t0 = time.time()
    # stdin is closed so a program waiting for keyboard input fails at once instead of hanging.
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        out_b, err_b = proc.communicate(timeout=TIMEOUT_SECONDS)
        code, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired:
        # Kill the whole tree: killing only powershell.exe leaves children (e.g. a web server the command
        # started) holding the output pipes open, and Loki then waited forever (measured 2026-11-16).
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            out_b, err_b = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out_b, err_b = b"", b""
        code, timed_out = None, True
    out = (out_b or b"").decode("utf-8", errors="replace")
    err = (err_b or b"").decode("utf-8", errors="replace")
    # Strip PowerShell's CLIXML progress noise from stderr.
    err = re.sub(r"#< CLIXML\s*<Objs.*?</Objs>", "", err, flags=re.S).strip()
    text = out.rstrip() + (("\n" if out.strip() else "") + err if err else "")
    truncated = len(text) > MAX_OUTPUT_CHARS
    return {"exit_code": code, "timed_out": timed_out, "duration_s": round(time.time() - t0, 2),
            "output": text[:MAX_OUTPUT_CHARS] + ("\n... (output cut)" if truncated else ""), "truncated": truncated}


async def run(command: str, token: str, cwd: str | None = None, prelude: str = "") -> dict[str, Any]:
    verdict = assess(command)
    if verdict["level"] in ("blocked", "admin"):
        raise PermissionError("Loki will not run this command. Copy it and run it yourself if you are sure.")
    if not token or not hmac.compare_digest(token, _token(command)):
        raise PermissionError("This command was not reviewed (or changed after review). Review it again.")
    workdir = cwd if cwd and Path(cwd).is_dir() else str(Path.home())
    result = await asyncio.to_thread(_run_blocking, command, workdir, prelude)
    entry = {"id": f"cmd-{int(time.time())}-{uuid.uuid4().hex[:6]}", "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "command": command, "level": verdict["level"], "cwd": workdir, "exit_code": result["exit_code"],
             "timed_out": result["timed_out"], "duration_s": result["duration_s"], "output_preview": result["output"][:2000]}
    _append_log(entry)
    return {**result, "id": entry["id"], "level": verdict["level"], "cwd": workdir}


def _append_log(entry: dict[str, Any]) -> None:
    ensure_data_dir()
    try:
        log = json.loads(LOG_FILE.read_text(encoding="utf-8")) if LOG_FILE.exists() else []
    except Exception:
        log = []
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log[-300:], indent=2), encoding="utf-8")


def recent(limit: int = 30) -> list[dict[str, Any]]:
    try:
        return list(reversed(json.loads(LOG_FILE.read_text(encoding="utf-8"))))[:limit] if LOG_FILE.exists() else []
    except Exception:
        return []
