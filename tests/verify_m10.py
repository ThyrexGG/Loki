"""Task 43 checks that need no model: code map, plan/review helpers, run_app, memory learning rules,
local tools (reminders, files, game checks, chat intents), hands-free and tools endpoint security, and the
reminder chat reply. Live model behaviour (plan quality, review, learning) is measured separately."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

from _isolated import base_url, test_data_dir  # refuses to run outside tests/run_tests.py

os.environ["LOKI_DATA_DIR"] = str(test_data_dir())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent, app_runner, code_map, local_tools  # noqa: E402
from app.memory import memory_store, wants_learning  # noqa: E402

BASE_URL = base_url()
H = {"X-Loki-Request": "1"}
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{(' - ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def main() -> int:
    print("=== Loki Task 43 verification: agent plan/map/run_app, memory, local tools (no model needed) ===")
    work = Path(os.environ["LOKI_PROJECTS_DIR"]) / "m10"
    work.mkdir(parents=True, exist_ok=True)

    print("[1] Code map")
    (work / "pkg").mkdir(exist_ok=True)
    (work / "pkg" / "store.py").write_text("import json\n\nclass Store:\n    def load(self, path):\n        pass\n\n"
                                           "def save_items(items, path):\n    pass\n", encoding="utf-8")
    (work / "app.js").write_text("import { x } from './util.js';\nexport function renderList(items) {}\n"
                                 "const onClick = (e) => {};\nclass Board {}\n", encoding="utf-8")
    m = code_map.build_map(work)
    check("python class + methods", "class Store" in m and "load(path)" in m, m)
    check("python function", "def save_items(items, path)" in m, m)
    check("js function / arrow / class / imports", all(s in m for s in ("renderList(items)", "onClick(e)", "Board", "imports ./util.js")), m)
    check("files_for_task finds by symbol", code_map.files_for_task(work, "fix save_items bug")[0].name == "store.py")

    print("[2] Plan and review helpers")
    check("plan for a build request", agent._wants_plan("build a flask app with a todo list and tests"))
    check("no plan for a question", not agent._wants_plan("what does main.py do?"))
    check("no plan for a one-liner", not agent._wants_plan("run it"))
    check("parse fenced JSON", agent._parse_json_reply({"message": {"content": '```json\n{"steps": ["a", "b"]}\n```'}}) == {"steps": ["a", "b"]})
    mat = agent._review_material("make a store", [("pkg/store.py", "+x")], work)
    check("review material shows the file", "class Store" in mat and "USER REQUEST" in mat)

    print("[3] run_app")
    for cmd, want in [("python app.py", True), ("python -m flask run", True), ("uvicorn main:app", True), ("node server.js", True),
                      ("npm start", True), ("python app.py; del x", False), ("Remove-Item x", False), ("python -c 'x'", False)]:
        check(f"allowed({cmd!r}) = {want}", app_runner.allowed(cmd) == want)
    check("policy lets run_app start servers", agent.command_policy("npm run dev", work, allow_server=True)[0] == "auto")
    check("run_command still refuses servers", agent.command_policy("npm run dev", work)[0] == "refuse")
    (work / "server.py").write_text(
        "import os, json\nfrom http.server import HTTPServer, BaseHTTPRequestHandler\n"
        "class H(BaseHTTPRequestHandler):\n    def do_GET(self):\n        b = json.dumps({'path': self.path}).encode()\n"
        "        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)\n"
        "    def log_message(self, *a):\n        pass\n"
        "HTTPServer(('127.0.0.1', int(os.environ.get('PORT', 5000))), H).serve_forever()\n", encoding="utf-8")
    started = app_runner.start(work, "python server.py", agent._PY_PRELUDE)
    check("app starts and listens", started.get("ok") is True, str(started)[:300])
    if started.get("ok"):
        got = app_runner.fetch("/api/items")
        check("GET on the running app", got.get("status") == 200 and "/api/items" in got.get("body", ""), str(got))
        check("status endpoint sees it", httpx.get(f"{BASE_URL}/api/agent/app", headers=H).status_code == 200)
        check("stop", app_runner.stop() and app_runner.status() is None)
    (work / "crash.py").write_text("raise SystemExit('boom')\n", encoding="utf-8")
    bad = app_runner.start(work, "python crash.py", agent._PY_PRELUDE)
    check("crashing app reported", bad.get("ok") is False and bad.get("exited") is True, str(bad)[:200])

    print("[4] Memory")
    memory_store.clear_all()
    for text, want in [("I'm a game dev working in Godot", True), ("my pc has an RTX 5050", True), ("I use VS Code", True),
                       ("what is the capital of France?", False), ("remember that I like short answers", False), ("explain recursion", False)]:
        check(f"wants_learning({text!r}) = {want}", wants_learning(text) == want)
    memory_store.add_memory("Editor", "The user uses VS Code.", "preference")
    check("near-identical memory merges", memory_store.add_memory("Editor", "The user uses VS Code!", "preference").get("duplicate") is True)
    check("different memory kept", not memory_store.add_memory("Engine", "The user makes games in Godot.").get("duplicate")
          and not memory_store.add_memory("Engine", "The user makes games in Unity.").get("duplicate"))
    first = memory_store.list_memories()[0]
    r = httpx.put(f"{BASE_URL}/api/memories/{first['memory_id']}", json={"content": "Edited text"}).json()
    check("edit memory over the API", r.get("ok") and r["memory"]["content"] == "Edited text", str(r))
    for i in range(14):
        memory_store.add_memory(f"fact {i}", f"The user collects item{i} and thing{i}.")
    ctx, n = memory_store.get_active_memory_context("tell me about item7")
    check("only relevant memories when there are many", n == 12 and "item7" in ctx and "VS Code" in ctx, f"n={n}")
    memory_store.clear_all()

    print("[5] Reminders")
    now = datetime(2026, 11, 20, 14, 30)  # a Friday
    for text, want in [("friday at 5 to submit", datetime(2026, 11, 20, 17, 0)), ("friday at 9am to x", datetime(2026, 11, 27, 9, 0)),
                       ("in 20 minutes to stretch", datetime(2026, 11, 20, 14, 50)), ("tomorrow at 9am call Sam", datetime(2026, 11, 21, 9, 0)),
                       ("monday morning about the demo", datetime(2026, 11, 23, 9, 0)), ("drink water", None)]:
        got, _ = local_tools.parse_when(text, now)
        check(f"parse_when({text!r})", got == want, f"got {got}")
    r = httpx.post(f"{BASE_URL}/api/chat/stream", json={"messages": [{"role": "user", "content": "remind me tomorrow at 9am to call Sam"}]}, timeout=30)
    evs = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    check("chat reminder answered without a model", [e["type"] for e in evs] == ["route", "tool_card", "token", "done"], str([e["type"] for e in evs]))
    lst = httpx.get(f"{BASE_URL}/api/tools/reminders", headers=H).json()["reminders"]
    check("reminder stored", any(x["text"] == "call Sam" for x in lst), str(lst))
    for x in lst:
        httpx.delete(f"{BASE_URL}/api/tools/reminders/{x['id']}", headers=H)

    print("[6] Chat intents")
    for text, want in [("remind me in 10 minutes to stretch", "reminder_add"), ("what reminders do I have?", "reminder_list"),
                       ("what's using my ram", "system"), ("why is my pc so slow", "system"),
                       ("check my godot project at D:\\Games\\Rogue", "game_check"), ("biggest files in D:\\Stuff", "largest"),
                       ("any duplicate photos in D:\\Photos?", "duplicates"), ("organise my downloads", "organise"),
                       ("write a python function to sort a list", None), ("how do I make a calendar app in react", None)]:
        got = local_tools.detect_intent(text)
        check(f"intent({text!r}) = {want}", (got or {}).get("tool") == want, str(got))

    print("[7] File tools")
    mess = work / "mess"
    mess.mkdir(exist_ok=True)
    (mess / "a.png").write_bytes(b"x" * 200_000)
    (mess / "b copy.png").write_bytes(b"x" * 200_000)
    (mess / "notes.txt").write_text("hi")
    check("largest", local_tools.largest_files(str(mess))["files"][0]["bytes"] == 200_000)
    check("duplicates", len(local_tools.duplicate_files(str(mess))["groups"]) == 1)
    plan = httpx.post(f"{BASE_URL}/api/tools/files/organise/plan", json={"folder": str(mess)}, headers=H).json()
    check("organise plan moves nothing yet", plan["count"] == 3 and (mess / "a.png").exists(), str(plan)[:200])
    ap = httpx.post(f"{BASE_URL}/api/tools/files/organise/apply", json={"plan_id": plan["plan_id"]}, headers=H).json()
    check("apply moves into type folders", ap.get("moved") == 3 and (mess / "Images" / "a.png").exists(), str(ap))
    un = httpx.post(f"{BASE_URL}/api/tools/files/organise/undo", json={"plan_id": ap["undo_id"]}, headers=H).json()
    check("undo puts them back", un.get("restored") == 3 and (mess / "a.png").exists() and not (mess / "Images").exists(), str(un))
    blocked = httpx.post(f"{BASE_URL}/api/tools/files/largest", json={"folder": "C:\\Windows"}, headers=H)
    check("system folders refused", blocked.status_code == 400)

    print("[8] Game project checks")
    g = work / "godot"
    (g / "scenes").mkdir(parents=True, exist_ok=True)
    (g / "project.godot").write_text('config/name="Rogue"\nconfig/features=PackedStringArray("4.3")\nrun/main_scene="res://scenes/main.tscn"\n')
    (g / "scenes" / "main.tscn").write_text('[ext_resource path="res://player.gd" id="1"]\n[ext_resource path="res://missing.png" id="2"]\n')
    (g / "player.gd").write_text('extends Node2D\n\nfunc _process(delta):\n\tvar s = get_node("Sprite")\n  \ts.rotate(delta)\n')
    rep = local_tools.check_game_project(str(g))
    whats = " ".join(i["what"] for i in rep["issues"])
    check("godot: missing resource", "missing.png" in whats)
    check("godot: mixed indentation", "tabs and spaces" in whats)
    check("godot: per-frame lookups", "every frame" in whats)
    u = work / "unity"
    (u / "Assets").mkdir(parents=True, exist_ok=True)
    (u / "ProjectSettings").mkdir(exist_ok=True)
    (u / "Assets" / "Mover.cs").write_text("using UnityEngine;\npublic class Player : MonoBehaviour {\n"
                                           "  void Update() {\n    var rb = GetComponent<Rigidbody>();\n  }\n}\n")
    rep = local_tools.check_game_project(str(u))
    whats = " ".join(i["what"] for i in rep["issues"])
    check("unity: class/file name mismatch", "does not match the file name" in whats, whats)
    check("unity: GetComponent in Update", "every frame" in whats, whats)
    check("unity: missing .meta", ".meta" in whats, whats)

    print("[9] Endpoint security (cross-site requests refused)")
    for method, path, body in [("get", "/api/tools/system", None), ("get", "/api/tools/reminders", None),
                               ("post", "/api/tools/files/largest", {"folder": str(mess)}),
                               ("post", "/api/voice/handsfree", {"enabled": True}), ("get", "/api/voice/handsfree/poll", None),
                               ("post", "/api/agent/app/stop", {}), ("get", "/api/agent/app", None)]:
        resp = httpx.request(method.upper(), f"{BASE_URL}{path}", json=body)
        check(f"{method.upper()} {path} without Loki header -> 403", resp.status_code == 403, str(resp.status_code))

    print(f"\n{'All checks passed.' if not failures else f'{len(failures)} check(s) FAILED: {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
