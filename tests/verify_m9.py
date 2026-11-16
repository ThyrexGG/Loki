"""Coding agent (ADR-016) checks that need no model: when the agent takes over, the "smart auto" command
rules, tool-call parsing, file tools and their guards, undo, project preview and endpoint security.
The live model behaviour is measured separately (see docs/WORK_LOG.md, Task 32)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

from _isolated import base_url, test_data_dir  # refuses to run outside tests/run_tests.py

# Import Loki's modules against the isolated data folder, never the real one.
os.environ["LOKI_DATA_DIR"] = str(test_data_dir())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent  # noqa: E402
from app import projects as project_store  # noqa: E402

BASE_URL = base_url()
H = {"X-Loki-Request": "1"}
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{(' - ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def main() -> int:
    print("=== Loki Task 32 verification: coding agent (no model needed) ===")
    assert "LOKI_PROJECTS_DIR" in os.environ, "run_tests.py must set LOKI_PROJECTS_DIR"
    assert agent.PROJECTS_HOME == Path(os.environ["LOKI_PROJECTS_DIR"]), agent.PROJECTS_HOME

    print("[1] When the agent takes over")
    for text, want in [("create a small website to demo ur skillset", True), ("make me a snake game in python", True),
                       ("build a todo app", True), ("write a script that renames my photos by date", True),
                       ("how do I reverse a list in python", False), ("what is a closure in javascript", False)]:
        check(f"wants_new_project({text!r}) = {want}", agent.wants_new_project(text) == want)
    for text, want in [("what does main.py do?", True), ("explain this project", True),
                       ("fix the failing test", False), ("can you add a dark mode?", False)]:
        check(f"_is_question({text!r}) = {want}", agent._is_question(text) == want)

    print("[2] Smart-auto command rules")
    root = Path(os.environ["LOKI_PROJECTS_DIR"]) / "policy-check"
    for cmd, want in [("python main.py", "auto"), ("python -m pytest -q", "auto"), ("Get-ChildItem", "auto"),
                      ("mkdir src", "auto"), ("npm install express", "ask"), ("pip install requests", "ask"),
                      ("Remove-Item old.txt", "ask"), ("git commit -m wip", "ask"), ("iwr https://example.com", "ask"),
                      ("Get-Content C:\\Windows\\win.ini", "ask"), ("type ..\\secret.txt", "ask"),
                      ("python -m http.server", "refuse"), ("npm run dev", "refuse"), ("Start-Process notepad", "refuse"),
                      ("format c:", "refuse"), ("sfc /scannow", "refuse")]:
        got, reasons = agent.command_policy(cmd, root)
        check(f"{cmd!r} -> {want}", got == want, f"got {got} {reasons}")

    print("[3] Reading tool calls")
    native = agent.extract_tool_calls({"tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}]})
    check("native tool_calls", native == [{"name": "read_file", "arguments": {"path": "a.py"}, "native": True}], str(native))
    text = agent.extract_tool_calls({"content": 'Sure: {"name": "write_file", "arguments": {"path": "a.py", "content": "x = 1\ny = 2"}}'})
    check("JSON in text with a raw newline (qwen2.5-coder style)", len(text) == 1 and text[0]["arguments"]["content"] == "x = 1\ny = 2", str(text))
    check("unknown tool ignored", agent.extract_tool_calls({"content": '{"name": "rm_rf", "arguments": {}}'}) == [])
    check("plain answer has no calls", agent.extract_tool_calls({"content": "All done, tests pass."}) == [])
    check("broken call detected", agent._looks_like_broken_call('{"name": "write_file", "arguments": {"path": "a.py", "content": "x'))
    check("code dumped instead of saved", agent._shows_work_instead_of_doing("```python\nprint(1)\n```", writes=0))
    check("short run hint in a summary is fine", not agent._shows_work_instead_of_doing("Run it with:\n```\npython main.py\n```", writes=2))
    check("announcing instead of doing", bool(agent._INTENT_ONLY.search("Thanks. I will update calc.py next.")))

    print("[3b] Checks that keep a small model honest")
    hp = Path(os.environ["LOKI_PROJECTS_DIR"]) / "hint-check"
    hp.mkdir(parents=True, exist_ok=True)
    hint = agent._failure_hint("E   ModuleNotFoundError: No module named 'convert_temperatures'", hp)
    check("missing module -> 'create it' hint", "convert_temperatures.py does not exist yet" in hint, hint)
    (hp / "index.html").write_text('<html><body><h2>Card 1 Title</h2><p>Card 1 content goes here.</p>'
                                   '<img src="card1.jpg"><footer>&copy; My Name</footer></body></html>', encoding="utf-8")
    issues = agent._site_issues(hp)
    check("page check: placeholder text", any("Placeholder" in i and "My Name" in i for i in issues), str(issues))
    check("page check: missing image", any("card1.jpg" in i for i in issues), str(issues))
    check("page check: no styling", any("no styling" in i for i in issues), str(issues))
    (hp / "index.html").write_text("<html><head><style>h1{}</style></head><body><h1>Rollcall</h1>"
                                   "<p>Take attendance in seconds.</p></body></html>", encoding="utf-8")
    check("page check: clean page passes", agent._site_issues(hp) == [], str(agent._site_issues(hp)))
    check("agent defaults to the benchmarked model", agent.AGENT_MODELS[0] == "qwen2.5:7b" or bool(os.environ.get("LOKI_AGENT_MODEL")))

    print("[4] File tools and guards")
    created = agent.create_project_folder("build a todo app")
    proj = Path(created)
    check("new project folder under LOKI_PROJECTS_DIR", proj.parent == agent.PROJECTS_HOME and proj.name == "todo-app", created)
    check("new project registered", created in [p["path"] for p in project_store.list_projects()])
    check("second folder gets a new name", Path(agent.create_project_folder("build a todo app")).name == "todo-app-2")
    r = agent.tool_list_files(proj, {})
    check("empty folder listed", r["ok"] and "empty" in r["result"])
    body = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n"
    w = agent.tool_write_file(created, proj, {"path": "src/ops.py", "content": "\n" + body})
    check("write_file creates a file in a new subfolder", w["ok"] and (proj / "src" / "ops.py").read_text(encoding="utf-8") == body, w.get("result", ""))
    check("leading blank line stripped", (proj / "src" / "ops.py").read_text(encoding="utf-8").startswith("def add"))
    changes = [w["change"]["id"]]
    check("placeholder marker refused", not agent.tool_write_file(created, proj, {"path": "b.py", "content": "<12 lines saved>"})["ok"])
    check("'rest unchanged' placeholder refused", not agent.tool_write_file(created, proj, {"path": "src/ops.py", "content": "def add(a, b):\n    return a + b\n# ... rest unchanged\n"})["ok"])
    shrink = agent.tool_write_file(created, proj, {"path": "src/ops.py", "content": "def add(a, b):\n    return a + b\n"})
    check("rewrite that deletes most of a file refused", not shrink["ok"] and "shrink" in shrink["result"], shrink["result"])
    rep = agent.tool_replace_in_file(created, proj, {"path": "src/ops.py", "old_text": "    return a - b", "new_text": "    return a - b  # subtract"})
    check("replace_in_file exact", rep["ok"] and "# subtract" in (proj / "src" / "ops.py").read_text(encoding="utf-8"), rep.get("result", ""))
    changes.append(rep["change"]["id"])
    loose = agent.tool_replace_in_file(created, proj, {"path": "src/ops.py", "old_text": "def mul(a, b):\nreturn a * b", "new_text": "def mul(a, b):\nreturn a * b * 1"})
    text = (proj / "src" / "ops.py").read_text(encoding="utf-8")
    check("replace_in_file tolerates wrong indentation", loose["ok"] and "    return a * b * 1" in text, loose.get("result", ""))
    changes.append(loose["change"]["id"])
    dup = agent.tool_write_file(created, proj, {"path": "dup.py", "content": "x = 1\nx = 1\n"})
    changes.append(dup["change"]["id"])
    check("ambiguous replace refused", not agent.tool_replace_in_file(created, proj, {"path": "dup.py", "old_text": "x = 1", "new_text": "x = 2"})["ok"])
    for bad in ("../escape.py", "C:/Windows/evil.py", ".env", "node_modules/x.js"):
        try:
            agent.tool_write_file(created, proj, {"path": bad, "content": "x"})
            check(f"write to {bad!r} refused", False)
        except project_store.ProjectError:
            check(f"write to {bad!r} refused", True)
    rd = agent.tool_read_file(proj, {"path": "src/ops.py", "start_line": 5, "end_line": 6})
    check("read_file line range", rd["ok"] and "def sub" in rd["result"] and "def add" not in rd["result"], rd["result"])
    check("search_files", "src/ops.py:5" in agent.tool_search_files(proj, {"query": "def sub"})["result"])
    snap, names = agent.project_snapshot(proj, "fix mul")
    check("project snapshot includes the code", "src/ops.py" in names and "def mul" in snap and "<untrusted_data" in snap, str(names))
    undo = agent.undo_changes(changes)
    check("undo all removes created files", not undo["failed"] and not (proj / "src" / "ops.py").exists() and not (proj / "dup.py").exists(), str(undo))

    print("[5] Endpoints")
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        for path, body in [("/api/agent/x/decide", {"approval_id": "a", "approve": True}), ("/api/agent/x/stop", {}),
                           ("/api/agent/undo", {"change_ids": []}), ("/api/agent/preview", {"path": created}),
                           ("/api/projects/open", {"path": created})]:
            check(f"{path} without the Loki header -> 403", c.post(path, json=body).status_code == 403)
        check("decide on an unknown run -> 404", c.post("/api/agent/nope/decide", json={"approval_id": "a", "approve": True}, headers=H).status_code == 404)
        site = proj.parent / "site-check"
        site.mkdir(exist_ok=True)
        (site / "index.html").write_text('<!DOCTYPE html><html><head><title>T</title><link rel="stylesheet" href="style.css">'
                                         '<link rel="stylesheet" href="https://cdn.example.com/x.css"></head><body><h1>Hi</h1>'
                                         '<img src="dot.svg"><script src="script.js"></script></body></html>', encoding="utf-8")
        (site / "style.css").write_text("h1 { color: rgb(1, 2, 3); }", encoding="utf-8")
        (site / "script.js").write_text("document.title = 'ran';", encoding="utf-8")
        (site / "dot.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>', encoding="utf-8")
        c.post("/api/projects", json={"path": str(site)}).raise_for_status()
        check("preview of an unregistered folder refused", c.post("/api/agent/preview", json={"path": "C:\\Windows"}, headers=H).status_code == 400)
        pv = c.post("/api/agent/preview", json={"path": str(site)}, headers=H)
        check("project preview created", pv.status_code == 200, pv.text)
        page = c.get(pv.json()["url"])
        html = page.text
        check("local CSS inlined", "<style>" in html and "rgb(1, 2, 3)" in html and 'href="style.css"' not in html)
        check("remote stylesheet left as is (and blocked by the CSP)", "https://cdn.example.com/x.css" in html)
        check("local JS inlined", "document.title = 'ran'" in html and 'src="script.js"' not in html)
        check("local image inlined as data URI", 'src="data:image/svg+xml;base64,' in html)
        csp = page.headers.get("content-security-policy", "")
        check("preview served with the sandbox CSP", "sandbox" in csp and "connect-src 'none'" in csp, csp)

    print(f"\n{'All coding-agent checks passed.' if not failures else f'{len(failures)} check(s) failed: {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
