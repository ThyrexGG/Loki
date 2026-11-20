"""Run the apps the coding agent builds (web servers, APIs) in the background and test them.

The agent's run_command only allows commands that finish within 60 s, so a Flask/FastAPI/Node server could
never be checked. run_app starts such a program as the user, in the project folder, on a free localhost
port, waits until it answers, requests a page and returns what came back. The app keeps running so the user
can open it from the chat ("Open app"), and is stopped when the next app starts, after 30 minutes, when the
user clicks Stop app, or when Loki shuts down. Only one app runs at a time.
"""

from __future__ import annotations

import atexit
import os
import re
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import DATA_DIR

LOG_DIR = DATA_DIR / "app_runs"
START_TIMEOUT_S = 25
MAX_LIFETIME_S = 30 * 60
RESERVED_PORTS = {8420, 11434}

# Programs the agent may start this way: the project's own code, run by a known runtime.
_LAUNCH = re.compile(
    r"^\s*(python3?|py)\s+(-m\s+(flask|uvicorn|http\.server|streamlit|gunicorn|waitress)\b.*|[\w./\\-]+\.py\b.*)$"
    r"|^\s*(flask\s+run|uvicorn\s+[\w.]+:\w+)\b.*$"
    r"|^\s*node\s+[\w./\\-]+\.(m?js|cjs)\b.*$"
    r"|^\s*(npm|pnpm|yarn)\s+(run\s+)?(start|dev|serve)\b.*$",
    re.I)
_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1?\]):(\d{2,5})", re.I)
_PORT_ARG = re.compile(r"(?:--port[ =]|-p\s+|port=|:)(\d{4,5})\b", re.I)


class AppRunError(Exception):
    pass


_current: dict[str, Any] | None = None


def allowed(command: str) -> bool:
    return bool(_LAUNCH.match(command.strip())) and not re.search(r"[;&|`]|\$\(", command)


def _free_port() -> int:
    for _ in range(20):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in RESERVED_PORTS:
            return port
    return 5173


def _listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _read_log(path: Path, limit: int = 3000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= limit else "... (start cut)\n" + text[-limit:]


def status() -> dict[str, Any] | None:
    global _current
    if not _current:
        return None
    proc: subprocess.Popen = _current["proc"]
    if proc.poll() is not None or time.time() - _current["started"] > MAX_LIFETIME_S:
        stop()
        return None
    return {k: v for k, v in _current.items() if k != "proc"}


def stop(app_id: str | None = None) -> bool:
    global _current
    if not _current or (app_id and _current["id"] != app_id):
        return False
    proc: subprocess.Popen = _current["proc"]
    if proc.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    _current = None
    return True


atexit.register(stop)


def start(root: Path, command: str, prelude: str = "") -> dict[str, Any]:
    """Start `command` in `root` and wait until it listens. Blocking: call it in a thread."""
    global _current
    command = command.strip()
    if not allowed(command):
        raise AppRunError("run_app only starts the project's own app, e.g. `python app.py`, `python -m flask run`, "
                          "`uvicorn main:app`, `node server.js` or `npm start`.")
    stop()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for old in sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)[:-10]:
        old.unlink(missing_ok=True)
    m = _PORT_ARG.search(command)
    port = int(m.group(1)) if m and int(m.group(1)) not in RESERVED_PORTS else _free_port()
    if re.match(r"^\s*(flask\s+run|python3?\s+-m\s+flask)", command, re.I) and "--port" not in command:
        command += f" --port {port}"
    if re.match(r"^\s*(uvicorn|python3?\s+-m\s+uvicorn)", command, re.I) and "--port" not in command:
        command += f" --port {port}"
    if re.match(r"^\s*python3?\s+-m\s+http\.server\s*$", command, re.I):
        command += f" {port} --bind 127.0.0.1"
    app_id = uuid.uuid4().hex[:10]
    log_path = LOG_DIR / f"{app_id}.log"
    env = {**os.environ, "PORT": str(port), "FLASK_RUN_PORT": str(port), "FLASK_RUN_HOST": "127.0.0.1",
           "HOST": "127.0.0.1", "PYTHONUNBUFFERED": "1", "BROWSER": "none"}
    log = open(log_path, "wb")
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", prelude + command],
        cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    log.close()
    _current = {"id": app_id, "proc": proc, "port": port, "command": command, "root": str(root),
                "log": str(log_path), "started": time.time(), "url": f"http://127.0.0.1:{port}/"}
    deadline = time.time() + START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            out = _read_log(log_path)
            _current = None
            return {"ok": False, "exited": True, "exit_code": proc.returncode, "port": port, "output": out}
        if _listening(port):
            break
        found = _URL.findall(_read_log(log_path, 20000))
        if found and int(found[-1]) not in RESERVED_PORTS and _listening(int(found[-1])):
            port = int(found[-1])
            _current.update(port=port, url=f"http://127.0.0.1:{port}/")
            break
        time.sleep(0.4)
    else:
        out = _read_log(log_path)
        stop()
        return {"ok": False, "timed_out": True, "port": port, "output": out}
    time.sleep(0.3)
    return {"ok": True, "id": app_id, "port": port, "url": _current["url"], "output": _read_log(log_path)}


def fetch(path: str = "/") -> dict[str, Any]:
    """GET a path on the running app (localhost only)."""
    cur = status()
    if not cur:
        raise AppRunError("No app is running.")
    path = "/" + str(path or "/").lstrip("/")
    if re.match(r"^/+[a-z]+:", path, re.I):
        raise AppRunError("Only paths on the running app can be requested.")
    url = f"http://127.0.0.1:{cur['port']}{path}"
    try:
        r = httpx.get(url, timeout=10.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        return {"ok": False, "url": url, "error": str(exc)}
    body = r.text
    return {"ok": r.status_code < 400, "url": url, "status": r.status_code,
            "content_type": r.headers.get("content-type", ""), "body": body[:2500] + ("\n... (cut)" if len(body) > 2500 else "")}
