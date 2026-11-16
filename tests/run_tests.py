"""Run Loki's verification suites against an isolated server.

    python tests\\run_tests.py          # all suites, gentle (default)
    python tests\\run_tests.py m3 m8    # some suites
    ... run_tests.py --fast             # full speed, no waiting (use when you are away from the PC)
    ... run_tests.py --keep             # keep the temp folder

Starts a second Loki server on a free localhost port with LOKI_DATA_DIR set to a fresh temporary
folder, runs each tests/verify_m*.py against it, then stops the server and deletes the folder.
Your real Loki (port 8420) and its data/ folder are never touched; the runner checks that by
fingerprinting data/ before and after.

Gentle mode (default) keeps the PC usable while the AI suites run: it waits until there is enough free
RAM and GPU memory before each AI suite, unloads the model and pauses after each one, runs at below-normal
priority and caps the CPU threads Ollama uses. A full run at full speed loaded several 8-9B models back to
back and made the PC lag and crash while other apps were open (2026-11-16).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DATA = REPO_ROOT / "data"
ALL_SUITES = [f"m{i}" for i in range(1, 10)]
MODEL_FREE = {"m9"}            # suites that never call a model: no waiting needed
NEED_RAM_GB = 4.0              # free RAM before an AI suite starts
NEED_VRAM_GB = 5.0             # free GPU memory before an AI suite starts (gemma2:9b is ~5.4 GB)
COOLDOWN_S = 8                 # pause after each AI suite
OLLAMA = "http://127.0.0.1:11434"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BELOW_NORMAL = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fingerprint(folder: Path) -> dict[str, str]:
    if not folder.exists():
        return {}
    return {
        str(p.relative_to(folder)): hashlib.md5(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*")) if p.is_file()
    }


def free_ram_gb() -> float | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullAvailPhys / 2**30
    except Exception:
        return None


def free_vram_gb() -> float | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW).stdout.strip().splitlines()[0]
        used, total = (float(x) for x in out.split(","))
        return (total - used) / 1024
    except Exception:
        return None


def unload_models() -> None:
    """Ask Ollama to drop every loaded model from memory (what Loki's Free VRAM button does)."""
    try:
        for m in httpx.get(f"{OLLAMA}/api/ps", timeout=5).json().get("models", []):
            httpx.post(f"{OLLAMA}/api/generate", json={"model": m["name"], "keep_alive": 0}, timeout=20)
    except (httpx.HTTPError, ValueError):
        pass


def wait_for_room(suite: str) -> None:
    """Block until the PC has enough free RAM and GPU memory for an AI suite."""
    last_note = 0.0
    while True:
        ram, vram = free_ram_gb(), free_vram_gb()
        short = []
        if ram is not None and ram < NEED_RAM_GB:
            short.append(f"{ram:.1f} GB RAM free (needs {NEED_RAM_GB:.0f})")
        if vram is not None and vram < NEED_VRAM_GB:
            short.append(f"{vram:.1f} GB GPU memory free (needs {NEED_VRAM_GB:.0f})")
        if not short:
            return
        if time.time() - last_note > 120:
            print(f"  ...  {suite}: waiting, the PC is busy: {' and '.join(short)}. Close some apps or games, "
                  "or press Ctrl+C to stop (add --fast to skip waiting).", flush=True)
            last_note = time.time()
        time.sleep(15)  # never unload here: the model in use may be the user's own Loki chat


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    fast = "--fast" in argv
    suites = [a for a in argv if not a.startswith("--")] or ALL_SUITES
    unknown = [s for s in suites if s not in ALL_SUITES]
    if unknown:
        print(f"Unknown suite(s): {unknown}. Choose from {ALL_SUITES}.")
        return 2

    work = Path(tempfile.mkdtemp(prefix="loki-test-"))
    data_dir, logs_dir = work / "data", work / "logs"
    data_dir.mkdir()
    logs_dir.mkdir()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    before = fingerprint(REAL_DATA)

    env = {**os.environ, "LOKI_DATA_DIR": str(data_dir), "PYTHONUTF8": "1", "LOKI_WEB_ACCESS": "0",
           "LOKI_PROJECTS_DIR": str(data_dir.parent / "projects")}
    if not fast:
        # Fewer CPU threads for the model and unload it soon after each answer.
        env["LOKI_OLLAMA_THREADS"] = str(max(2, (os.cpu_count() or 8) // 4))
        env["LOKI_OLLAMA_KEEP_ALIVE"] = "30s"
    flags = NO_WINDOW | (0 if fast else BELOW_NORMAL)
    print(f"Mode: {'fast (full speed)' if fast else 'gentle (waits for free memory, one model at a time, low priority)'}")
    server_log = open(logs_dir / "server.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT, creationflags=flags,
    )
    results: list[tuple[str, bool, float]] = []
    try:
        deadline = time.time() + 45
        while True:
            try:
                if httpx.get(f"{url}/static/loki.png", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if server.poll() is not None or time.time() > deadline:
                print(f"Isolated server failed to start. Log: {logs_dir / 'server.log'}")
                keep = True
                return 1
            time.sleep(0.4)
        print(f"Isolated Loki on {url}  |  throwaway data: {data_dir}\n")

        test_env = {**env, "LOKI_TEST_URL": url, "LOKI_TEST_DATA_DIR": str(data_dir)}
        test_env.pop("LOKI_DATA_DIR", None)
        for suite in suites:
            uses_model = suite not in MODEL_FREE
            if uses_model and not fast:
                wait_for_room(suite)
            script = REPO_ROOT / "tests" / f"verify_{suite}.py"
            log = logs_dir / f"{suite}.log"
            t0 = time.time()
            with open(log, "w", encoding="utf-8") as fh:
                rc = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, env=test_env,
                                    stdout=fh, stderr=subprocess.STDOUT, timeout=1800, creationflags=flags).returncode
            ok = rc == 0
            results.append((suite, ok, time.time() - t0))
            print(f"  {'PASS' if ok else 'FAIL'}  {suite}  ({time.time() - t0:.0f}s)", flush=True)
            if not ok:
                keep = True
                tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
                print("        " + "\n        ".join(tail))
            if uses_model and not fast:
                unload_models()
                time.sleep(COOLDOWN_S)
    except KeyboardInterrupt:
        print("\nStopped by you.")
        keep = True
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
        if not fast:
            unload_models()

    after = fingerprint(REAL_DATA)
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} suites passed.")
    if before == after:
        print("Real data/ folder: untouched (identical before and after).")
    else:
        changed = sorted(set(before) ^ set(after) | {k for k in before.keys() & after.keys() if before[k] != after[k]})
        print(f"NOTE: real data/ changed during the run: {changed}. The tests never write there, "
              "so this was most likely you using Loki at the same time.")
    if keep:
        print(f"Kept test folder for inspection: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if passed == len(results) and len(results) == len(suites) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
