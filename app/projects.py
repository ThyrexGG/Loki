"""Project folders for coding help (ADR-012): context for chat, reviewed edits, backups and undo.

Safety model ("Loki proposes, you approve"):
- Loki only reads and writes inside project folders the user added explicitly.
- Every write is triggered by the user clicking Apply on a reviewed diff; the previous version is
  backed up under data/backups/ and the change is logged in data/project_changes.json (undoable).
- Paths are resolved and must stay inside the project (no "..", no absolute paths, no symlink escapes).
- Secrets and bulky folders are never read: .env*, keys, .git, node_modules, virtualenvs, build output.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ensure_data_dir, load_settings, save_settings

BACKUP_DIR = DATA_DIR / "backups"
CHANGES_FILE = DATA_DIR / "project_changes.json"

IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", ".env", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".idea", ".vscode", "dist", "build", "out", "target", "bin", "obj",
    ".next", ".nuxt", ".cache", "coverage", ".gradle", "Library", "Temp", "Logs", ".vs", "packages",
}
TEXT_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".html", ".htm", ".css", ".scss", ".md",
    ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".ps1", ".psm1", ".bat", ".cmd", ".sh", ".c", ".h",
    ".cpp", ".hpp", ".cc", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".lua", ".luau", ".sql",
    ".xml", ".csproj", ".sln", ".gd", ".shader", ".hlsl", ".glsl", ".vue", ".svelte", ".swift", ".dart",
    ".r", ".m", ".gradle", ".properties", ".csv", ".env.example", ".gitignore", ".editorconfig",
}
SECRET_NAME = re.compile(r"(^\.env($|\.(?!example))|secret|credential|\.pem$|\.key$|\.pfx$|\.p12$|id_rsa)", re.I)
MAX_FILE_BYTES = 200_000
MAX_FILES = 3000
BLOCKED_ROOTS = {"C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users"}


class ProjectError(Exception):
    pass


# ---------------------------------------------------------------------------
# Folder registry
# ---------------------------------------------------------------------------
def list_projects() -> list[dict[str, Any]]:
    out = []
    for p in load_settings().get("project_folders", []):
        path = Path(p)
        out.append({"path": str(path), "name": path.name or str(path), "exists": path.is_dir()})
    return out


def add_project(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip().strip('"')
    if not raw:
        raise ProjectError("Enter a folder path.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ProjectError("Use a full folder path, for example C:\\Users\\you\\Projects\\my-app.")
    path = path.resolve()
    if not path.is_dir():
        raise ProjectError("That folder does not exist.")
    if str(path).rstrip("\\") in {r.rstrip("\\") for r in BLOCKED_ROOTS} or len(path.parts) <= 1:
        raise ProjectError("Pick a specific project folder, not a drive or system folder.")
    if DATA_DIR.resolve() == path or DATA_DIR.resolve() in path.parents:
        raise ProjectError("Loki's own data folder cannot be a project.")
    settings = load_settings()
    folders = settings.get("project_folders", [])
    if str(path) not in folders:
        folders.append(str(path))
    settings["project_folders"] = folders
    save_settings(settings)
    return {"path": str(path), "name": path.name, "exists": True}


def remove_project(raw: str) -> None:
    settings = load_settings()
    settings["project_folders"] = [p for p in settings.get("project_folders", []) if p != raw]
    save_settings(settings)


def get_project_root(raw: str) -> Path:
    if raw not in load_settings().get("project_folders", []):
        raise ProjectError("This folder is not one of your projects.")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise ProjectError("The project folder no longer exists.")
    return root


def resolve_inside(root: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.startswith(("/", "~")) or re.match(r"^[a-zA-Z]:", rel) or any(part == ".." for part in rel.split("/")):
        raise ProjectError("File paths must be relative to the project folder.")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ProjectError("That path is outside the project folder.")
    if SECRET_NAME.search(target.name):
        raise ProjectError("Loki does not read or write secret files such as .env or keys.")
    if any(part in IGNORE_DIRS for part in target.relative_to(root).parts[:-1]):
        raise ProjectError("Loki does not edit files inside dependency, build or version-control folders.")
    return target


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _is_text_file(p: Path) -> bool:
    name = p.name.lower()
    return (p.suffix.lower() in TEXT_EXT or name in TEXT_EXT or name in {"dockerfile", "makefile", "readme", "license"})


def iter_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if not _is_text_file(p) or SECRET_NAME.search(fn):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p
            count += 1
            if count >= MAX_FILES:
                return


def file_tree(root: Path, max_lines: int = 120) -> str:
    rels = [p.relative_to(root).as_posix() for p in iter_files(root)]
    lines = rels[:max_lines]
    if len(rels) > max_lines:
        lines.append(f"... and {len(rels) - max_lines} more files")
    return "\n".join(lines)


_STOP = set("the a an and or to of in on for with this that it is are be can how what why where when which "
            "my me i you your please make add fix change update use using file files code project function".split())


def _terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_.\-/]{2,}", question)
    return [w.lower() for w in words if w.lower() not in _STOP][:25]


def relevant_files(root: Path, question: str, limit: int = 3) -> list[Path]:
    terms = _terms(question)
    mentioned = {t.split("/")[-1] for t in terms if "." in t}
    scored = []
    for p in iter_files(root):
        rel = p.relative_to(root).as_posix().lower()
        score = 0.0
        if p.name.lower() in mentioned or rel in terms:
            score += 100
        score += sum(6 for t in terms if t in rel)
        if score < 100 and terms:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            score += sum(min(text.count(t), 5) for t in terms)
        if score > 0:
            scored.append((score, -len(rel), p))
    scored.sort(reverse=True)
    return [p for _, _, p in scored[:limit]]


def build_context(raw_root: str, question: str, budget_chars: int = 9000) -> tuple[str, list[str]]:
    """Return (context text for the model, list of relative files included)."""
    root = get_project_root(raw_root)
    tree = file_tree(root)
    parts = [f"PROJECT FOLDER: {root.name}\nFILES:\n{tree}"]
    used = len(parts[0])
    included = []
    for p in relevant_files(root, question):
        rel = p.relative_to(root).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        room = budget_chars - used - 200
        if room < 800:
            break
        clipped = text if len(text) <= room else text[:room] + "\n... (file continues; ask for the rest if needed)"
        lang = p.suffix.lstrip(".") or "text"
        block = f"\nFILE {rel} ({len(text.splitlines())} lines):\n```{lang}\n{clipped}\n```"
        parts.append(block)
        used += len(block)
        included.append(rel)
    return "\n".join(parts), included


EDIT_INSTRUCTIONS = (
    "To change or create a file, explain the change in one or two sentences, then give the COMPLETE new "
    "content of that file in a fenced code block whose info string is file:<relative/path>, for example:\n"
    "```file:src/app.py\n<entire file content>\n```\n"
    "Always include the whole file (never '...' or 'rest unchanged'), one block per file, paths relative to "
    "the project folder. The user reviews a diff and applies it themselves; you cannot run commands or write files."
)


# ---------------------------------------------------------------------------
# Reviewed edits: diff -> apply (with backup) -> undo
# ---------------------------------------------------------------------------
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def preview_change(raw_root: str, rel: str, new_content: str) -> dict[str, Any]:
    root = get_project_root(raw_root)
    target = resolve_inside(root, rel)
    exists = target.exists()
    if exists and not target.is_file():
        raise ProjectError("That path is a folder, not a file.")
    old = target.read_text(encoding="utf-8", errors="replace") if exists else ""
    new = new_content.replace("\r\n", "\n")
    if old.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    old_lines, new_lines = old.splitlines(), new.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="", n=3))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    warnings = []
    if exists and old_lines and len(new_lines) < 0.5 * len(old_lines) and len(old_lines) > 20:
        warnings.append(f"This shrinks the file from {len(old_lines)} to {len(new_lines)} lines. "
                        "The model may have left parts out; check before applying.")
    if re.search(r"^\s*(//|#|<!--)?\s*\.\.\.\s*(rest|existing|unchanged|remaining)", new, re.I | re.M):
        warnings.append("The new version contains a placeholder like '... rest unchanged'. Applying it would delete that code.")
    low_rel = rel.lower()
    if low_rel.endswith(".py") and new.strip():
        import ast
        try:
            ast.parse(new, filename=rel)
        except SyntaxError as exc:
            warnings.append(f"Python syntax error on line {exc.lineno}: {exc.msg}.")
    elif low_rel.endswith(".json") and new.strip():
        try:
            json.loads(new)
        except json.JSONDecodeError as exc:
            warnings.append(f"JSON syntax error on line {exc.lineno}, col {exc.colno}: {exc.msg}.")
    return {
        "path": rel, "exists": exists, "is_new": not exists, "diff": "\n".join(diff), "added": added,
        "removed": removed, "unchanged": old == new, "warnings": warnings, "base_sha": _sha(old),
        "old_lines": len(old_lines), "new_lines": len(new_lines),
    }


def _load_changes() -> list[dict[str, Any]]:
    if not CHANGES_FILE.exists():
        return []
    try:
        data = json.loads(CHANGES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_changes(changes: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    CHANGES_FILE.write_text(json.dumps(changes[-500:], indent=2), encoding="utf-8")


def apply_change(raw_root: str, rel: str, new_content: str, base_sha: str) -> dict[str, Any]:
    root = get_project_root(raw_root)
    target = resolve_inside(root, rel)
    old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    if _sha(old) != base_sha:
        raise ProjectError("The file changed since you reviewed it. Review the change again.")
    preview = preview_change(raw_root, rel, new_content)
    change_id = f"chg-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    backup = None
    if target.exists():
        backup = BACKUP_DIR / change_id / Path(rel.replace("\\", "/"))
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(target.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    new = new_content.replace("\r\n", "\n")
    if old.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    # Keep the file's existing line endings (read_text() hides CRLF, so check the raw bytes).
    if backup is not None and b"\r\n" in backup.read_bytes():
        new = new.replace("\n", "\r\n")
    target.write_text(new, encoding="utf-8", newline="")
    changes = _load_changes()
    entry = {
        "id": change_id, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "project": str(root), "path": rel,
        "created": backup is None, "backup": str(backup) if backup else None,
        "added": preview["added"], "removed": preview["removed"], "undone": False,
        "after_sha": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    changes.append(entry)
    _save_changes(changes)
    return entry


def undo_change(change_id: str) -> dict[str, Any]:
    changes = _load_changes()
    entry = next((c for c in changes if c["id"] == change_id), None)
    if entry is None:
        raise ProjectError("Change not found.")
    if entry.get("undone"):
        raise ProjectError("This change was already undone.")
    root = get_project_root(entry["project"])
    target = resolve_inside(root, entry["path"])
    current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if current != entry.get("after_sha"):
        raise ProjectError("The file was changed after Loki's edit, so undoing now would overwrite your newer work.")
    if entry["created"]:
        if target.exists():
            target.unlink()
    else:
        target.write_bytes(Path(entry["backup"]).read_bytes())
    entry["undone"] = True
    _save_changes(changes)
    return entry


def list_changes(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_load_changes()))[:limit]
