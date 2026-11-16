"""Run Loki's verification suites against an isolated server.

    python tests\\run_tests.py          # all suites
    python tests\\run_tests.py m3 m8    # some suites
    ... run_tests.py --keep                                                          # keep temp folder

Starts a second Loki server on a free localhost port with LOKI_DATA_DIR set to a fresh temporary
folder, runs each tests/verify_m*.py against it, then stops the server and deletes the folder.
Your real Loki (port 8420) and its data/ folder are never touched; the runner checks that by
fingerprinting data/ before and after. Ollama is shared, so close games or other GPU-heavy apps
first or the AI steps may time out.
"""

from __future__ import annotations

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
ALL_SUITES = [f"m{i}" for i in range(1, 9)]


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


def gpu_warning() -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip().splitlines()[0]
        used, total = (float(x) for x in out.split(","))
        if used > 0.4 * total:
            return (f"GPU memory already {used:.0f} / {total:.0f} MiB in use (a game or another app?). "
                    "AI steps may be slow or time out.")
    except Exception:
        return None
    return None


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    suites = [a for a in argv if not a.startswith("--")] or ALL_SUITES
    unknown = [s for s in suites if s not in ALL_SUITES]
    if unknown:
        print(f"Unknown suite(s): {unknown}. Choose from {ALL_SUITES}.")
        return 2

    warn = gpu_warning()
    if warn:
        print(f"WARNING: {warn}\n")

    work = Path(tempfile.mkdtemp(prefix="loki-test-"))
    data_dir, logs_dir = work / "data", work / "logs"
    data_dir.mkdir()
    logs_dir.mkdir()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    before = fingerprint(REAL_DATA)

    env = {**os.environ, "LOKI_DATA_DIR": str(data_dir), "PYTHONUTF8": "1", "LOKI_WEB_ACCESS": "0"}
    server_log = open(logs_dir / "server.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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
            script = REPO_ROOT / "tests" / f"verify_{suite}.py"
            log = logs_dir / f"{suite}.log"
            t0 = time.time()
            with open(log, "w", encoding="utf-8") as fh:
                rc = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, env=test_env,
                                    stdout=fh, stderr=subprocess.STDOUT, timeout=1200).returncode
            ok = rc == 0
            results.append((suite, ok, time.time() - t0))
            print(f"  {'PASS' if ok else 'FAIL'}  {suite}  ({time.time() - t0:.0f}s)")
            if not ok:
                keep = True
                tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
                print("        " + "\n        ".join(tail))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()

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
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
