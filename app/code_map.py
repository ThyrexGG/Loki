"""Compact map of a project's code: which files define which classes and functions, and what they import.

Small local models cannot read a whole project, so the coding agent gets this map up front (a few
thousand characters) and picks the files to read from it, instead of guessing from file names.
Python is parsed with `ast`; JavaScript/TypeScript, C#, GDScript and others use simple patterns.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app import projects as project_store

_JS_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|[A-Za-z_$][\w$]*)\s*=>", re.M),
]
_JS_IMPORT = re.compile(r"""(?:import\s[^'"]*from\s*|require\()\s*['"]([^'"]+)['"]""")
_CS_PATTERNS = [
    re.compile(r"^\s*(?:public|internal|private|protected)?\s*(?:static\s+|sealed\s+|abstract\s+|partial\s+)*(?:class|struct|interface|enum)\s+(\w+)", re.M),
    re.compile(r"^\s*(?:public|private|protected|internal)\s+(?:static\s+|override\s+|virtual\s+|async\s+)*[\w<>\[\],.]+\s+(\w+)\s*\(([^)]*)\)", re.M),
]
_GD_PATTERNS = [
    re.compile(r"^class_name\s+(\w+)", re.M),
    re.compile(r"^(?:static\s+)?func\s+(\w+)\s*\(([^)]*)\)", re.M),
    re.compile(r"^signal\s+(\w+)", re.M),
]
_CSS_RULE = re.compile(r"^([.#][\w-]+)[^{]*\{", re.M)
_HTML_ID = re.compile(r"""\bid=["']([\w-]+)["']""")

MAP_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".cs", ".gd", ".css", ".html", ".htm"}


def _py_outline(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"(syntax error on line {exc.lineno})"]
    out: list[str] = []
    imports: list[str] = []

    def sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        names = [a.arg for a in fn.args.args]
        if fn.args.vararg:
            names.append("*" + fn.args.vararg.arg)
        if fn.args.kwarg:
            names.append("**" + fn.args.kwarg.arg)
        return f"{'async ' if isinstance(fn, ast.AsyncFunctionDef) else ''}{fn.name}({', '.join(names)})"

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"def {sig(node)}  L{node.lineno}")
        elif isinstance(node, ast.ClassDef):
            methods = [sig(n).replace("(self, ", "(").replace("(self)", "()")
                       for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            out.append(f"class {node.name}  L{node.lineno}" + (": " + ", ".join(methods[:12]) if methods else ""))
        elif isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(("." * node.level) + node.module)
        elif isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            out.append(f"runs as a script  L{node.lineno}")
    if imports:
        out.insert(0, "imports " + ", ".join(dict.fromkeys(imports)))
    return out


def _regex_outline(text: str, patterns: list[re.Pattern]) -> list[str]:
    found: list[tuple[int, str]] = []
    for pat in patterns:
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            name = m.group(1)
            args = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) is not None else None
            found.append((line, f"{name}({' '.join(args.split())})  L{line}" if args is not None else f"{name}  L{line}"))
    return [s for _, s in sorted(found)]


def outline(path: Path, text: str) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".py":
        return _py_outline(text)
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
        items = _regex_outline(text, _JS_PATTERNS)
        imports = list(dict.fromkeys(_JS_IMPORT.findall(text)))
        return (["imports " + ", ".join(imports[:10])] if imports else []) + items
    if ext == ".cs":
        return _regex_outline(text, _CS_PATTERNS)
    if ext == ".gd":
        return _regex_outline(text, _GD_PATTERNS)
    if ext == ".css":
        sels = list(dict.fromkeys(_CSS_RULE.findall(text)))
        return ["selectors " + " ".join(sels[:30])] if sels else []
    if ext in (".html", ".htm"):
        ids = list(dict.fromkeys(_HTML_ID.findall(text)))
        return ["ids " + " ".join("#" + i for i in ids[:30])] if ids else []
    return []


def build_map(root: Path, budget: int = 5000) -> str:
    """Text map of the project, at most `budget` characters. Empty for projects with no code files."""
    lines: list[str] = []
    used = 0
    for p in sorted(project_store.iter_files(root), key=lambda q: (len(q.relative_to(root).parts), q.as_posix())):
        if p.suffix.lower() not in MAP_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        items = outline(p, text)
        block = f"{rel} ({len(text.splitlines())} lines)" + "".join(f"\n  {i}" for i in items[:25])
        if used + len(block) > budget:
            lines.append(f"... (more files; use list_files and search_files)")
            break
        lines.append(block)
        used += len(block) + 1
    return "\n".join(lines)


def files_for_task(root: Path, task: str, limit: int = 4) -> list[Path]:
    """Files whose names or defined symbols match words in the task (code-map aware relevance)."""
    terms = [t for t in re.findall(r"[A-Za-z_][\w.]{2,}", task.lower())]
    if not terms:
        return project_store.relevant_files(root, task, limit=limit)
    scored: list[tuple[float, Path]] = []
    for p in project_store.iter_files(root):
        if p.suffix.lower() not in MAP_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        symbols = " ".join(outline(p, text)).lower()
        rel = p.relative_to(root).as_posix().lower()
        score = sum(8 for t in terms if t in rel) + sum(4 for t in terms if t in symbols)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    picked = [p for _, p in scored[:limit]]
    for p in project_store.relevant_files(root, task, limit=limit):
        if len(picked) >= limit:
            break
        if p not in picked:
            picked.append(p)
    return picked
