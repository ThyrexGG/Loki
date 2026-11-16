"""Narrowly scoped, read-only project/folder analysis tools and natural-language workflow planner."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, DATA_DIR

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache"}

CODE_EXTS = {".py", ".js", ".ts", ".html", ".css", ".ps1", ".bat", ".sh", ".luau", ".lua", ".cs", ".cpp", ".h", ".rs", ".go"}
DOC_EXTS = {".md", ".txt", ".rst", ".pdf", ".doc", ".docx"}
DATA_EXTS = {".json", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".db", ".sqlite", ".log"}
ASSET_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".fbx", ".obj", ".blend", ".wav", ".mp3", ".ogg"}


def _is_forbidden_system_dir(path: Path) -> bool:
    """Prevent broad scans of OS system directories or root drives."""
    resolved = str(path.resolve()).lower().rstrip("\\/")
    if len(resolved) <= 3:  # e.g., "c:"
        return True
    forbidden_prefixes = (
        r"c:\windows",
        r"c:\program files",
        r"c:\program files (x86)",
        r"c:\programdata",
    )
    return any(resolved.startswith(p) for p in forbidden_prefixes)


def scan_project_directory(folder_path: str | None = None, max_files: int = 500) -> dict[str, Any]:
    """
    Read-only project/game directory scanner.
    Counts files by extension/category, identifies top 10 largest files/assets,
    and lists the 10 most recently modified files without modifying anything on disk.
    """
    raw = (folder_path or "").strip()
    target = Path(raw) if raw else BASE_DIR
    try:
        resolved = target.resolve()
    except Exception as exc:
        return {"ok": False, "error": f"Invalid folder path: {exc}"}

    if not resolved.exists() or not resolved.is_dir():
        return {"ok": False, "error": f"Folder not found: {resolved}"}

    if _is_forbidden_system_dir(resolved):
        return {
            "ok": False,
            "error": f"Blocked by Loki Scope Boundary: Scanning OS system directory '{resolved}' is not allowed.",
        }

    ext_counts: dict[str, int] = {}
    category_bytes: dict[str, int] = {
        "code_and_scripts": 0,
        "docs_and_notes": 0,
        "data_and_configs": 0,
        "media_and_assets": 0,
        "other": 0,
    }
    all_files: list[dict[str, Any]] = []
    total_bytes = 0

    for item in resolved.rglob("*"):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if not item.is_file():
            continue
        try:
            st = item.stat()
        except Exception:
            continue

        ext = item.suffix.lower() or "(no_ext)"
        size = int(st.st_size)
        mtime = float(st.st_mtime)
        rel = str(item.relative_to(resolved))

        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        total_bytes += size

        if ext in CODE_EXTS:
            category_bytes["code_and_scripts"] += size
        elif ext in DOC_EXTS:
            category_bytes["docs_and_notes"] += size
        elif ext in DATA_EXTS:
            category_bytes["data_and_configs"] += size
        elif ext in ASSET_EXTS:
            category_bytes["media_and_assets"] += size
        else:
            category_bytes["other"] += size

        all_files.append(
            {
                "name": item.name,
                "relative_path": rel,
                "extension": ext,
                "size_bytes": size,
                "modified_iso": datetime.fromtimestamp(mtime, tz=timezone.utc)
                .astimezone()
                .isoformat(timespec="seconds"),
                "mtime": mtime,
            }
        )
        if len(all_files) >= max_files:
            break

    largest = sorted(all_files, key=lambda x: x["size_bytes"], reverse=True)[:10]
    recent = sorted(all_files, key=lambda x: x["mtime"], reverse=True)[:10]
    sorted_exts = dict(sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True))

    lines = [
        f"PROJECT FOLDER: {resolved}",
        f"TOTAL FILES SCANNED: {len(all_files)} (Total Size: {round(total_bytes / 1024, 1)} KB)",
        "EXTENSION BREAKDOWN: " + ", ".join(f"{k}: {v}" for k, v in sorted_exts.items()),
        "CATEGORY BYTES: " + ", ".join(f"{k}={v} B" for k, v in category_bytes.items()),
        "",
        "TOP 10 LARGEST FILES / ASSETS:",
    ]
    for f in largest:
        lines.append(f"  - {f['relative_path']} ({f['size_bytes']} B, ext={f['extension']})")

    lines.append("\nTOP 10 MOST RECENTLY MODIFIED FILES:")
    for f in recent:
        lines.append(f"  - {f['relative_path']} (modified {f['modified_iso']}, {f['size_bytes']} B)")

    return {
        "ok": True,
        "folder_path": str(resolved),
        "total_files": len(all_files),
        "total_bytes": total_bytes,
        "extension_counts": sorted_exts,
        "category_bytes": category_bytes,
        "largest_files": largest,
        "recent_files": recent,
        "formatted_summary": "\n".join(lines),
    }


def build_folder_organization_preview(folder_path: str | None = None, max_files: int = 200) -> dict[str, Any]:
    """
    Read-only folder organization planner.
    Inspects files in a selected folder and builds a deterministic, non-destructive
    proposed folder structure without moving, renaming, or deleting any files.
    """
    raw = (folder_path or "").strip()
    target = Path(raw) if raw else DATA_DIR
    try:
        resolved = target.resolve()
    except Exception as exc:
        return {"ok": False, "error": f"Invalid folder path: {exc}"}

    if not resolved.exists() or not resolved.is_dir():
        return {"ok": False, "error": f"Folder not found: {resolved}"}

    if _is_forbidden_system_dir(resolved):
        return {
            "ok": False,
            "error": f"Blocked by Loki Scope Boundary: Organizing OS system directory '{resolved}' is not allowed.",
        }

    proposals: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}

    for item in sorted(resolved.rglob("*")):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if not item.is_file():
            continue
        try:
            size = int(item.stat().st_size)
        except Exception:
            continue

        ext = item.suffix.lower()
        rel = str(item.relative_to(resolved))
        if ext in CODE_EXTS:
            bucket = "01_Code_and_Scripts"
        elif ext in DOC_EXTS:
            bucket = "02_Documents_and_Notes"
        elif ext in DATA_EXTS:
            bucket = "03_Data_and_Logs"
        elif ext in ASSET_EXTS:
            bucket = "04_Media_and_Assets"
        else:
            bucket = "05_Archives_and_Misc"

        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        proposals.append(
            {
                "file_name": item.name,
                "current_relative_path": rel,
                "proposed_folder": f"{bucket}/{item.name}",
                "size_bytes": size,
                "extension": ext or "(none)",
            }
        )
        if len(proposals) >= max_files:
            break

    lines = [
        f"SELECTED SOURCE FOLDER (READ-ONLY INVENTORY): {resolved}",
        f"FILES INVENTORIED: {len(proposals)}",
        "PROPOSED CATEGORY BUCKETS: " + ", ".join(f"{k} ({v} files)" for k, v in bucket_counts.items()),
        "",
        "DETERMINISTIC FILE MAPPING PREVIEW (NO FILES MOVED ON DISK):",
    ]
    for p in proposals[:60]:
        lines.append(
            f"  - {p['current_relative_path']} ({p['size_bytes']} B) -> {p['proposed_folder']}"
        )

    return {
        "ok": True,
        "folder_path": str(resolved),
        "files_count": len(proposals),
        "bucket_counts": bucket_counts,
        "proposals": proposals,
        "formatted_preview": "\n".join(lines),
    }


def plan_workflow_from_natural_language(
    prompt: str, workflow_definitions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """
    Turn a plain-English user job description into an inspectable workflow plan,
    pre-filling inputs and highlighting permissions and approval points.
    """
    clean = (prompt or "").strip()
    if not clean:
        return {"ok": False, "error": "Describe a job in plain English first."}

    lower = clean.lower()

    # Extract any explicit Windows path if present in the user's prompt
    path_match = re.search(r"([a-zA-Z]:\\[^\s\"']+)", clean)
    extracted_path = path_match.group(1) if path_match else ""

    selected_id = "pc_health_audit"
    reason = "Matched hardware/system health diagnostic keywords."
    suggested_inputs: dict[str, Any] = {
        "focus_question": clean,
        "include_windows_events": "event" in lower or "warning" in lower or "error" in lower,
    }

    if any(k in lower for k in ("csv", "spreadsheet", "excel", "table", "duplicate row")):
        selected_id = "clean_csv_to_new_copy"
        reason = "Matched spreadsheet/CSV cleaning intent (uses deterministic pandas cleaner + Preview & Approval Gate)."
        suggested_inputs["csv_file_path"] = extracted_path or str(DATA_DIR / "sample_messy_tasks.csv")
    elif any(k in lower for k in ("organize", "sort", "clean folder", "categorize", "messy folder", "folder plan", "tidy")):
        selected_id = "folder_organization_plan"
        reason = "Matched folder organization intent (read-only inventory + non-destructive organization manifest via Approval Gate)."
        suggested_inputs["target_folder_path"] = extracted_path or str(DATA_DIR)
    elif any(k in lower for k in ("game", "build report", "project audit", "asset", "codebase", "repo")):
        selected_id = "game_dev_project_audit"
        reason = "Matched game/code project build & asset audit intent (read-only folder scan + Approval Gate export)."
        suggested_inputs["project_folder_path"] = extracted_path or str(BASE_DIR)
    elif any(k in lower for k in ("video", "youtube", "publish", "chapter", "content kit", "description", "tags")):
        selected_id = "content_publishing_kit"
        reason = "Matched video/content publishing preparation intent (retrieves approved indexed notes + drafts publishing kit via Approval Gate)."
    elif any(k in lower for k in ("export report", "save report", "markdown report", "write report")):
        selected_id = "export_research_report"
        reason = "Matched cited research report export intent (pauses at Preview & Approval Gate before writing to data/exports/)."
    elif any(k in lower for k in ("research", "digest", "indexed", "docs", "document", "summarize folder")):
        selected_id = "folder_research_digest"
        reason = "Matched local indexed folder research digest intent (read-only cited synthesis)."
    elif any(k in lower for k in ("log", ".log", "tail", "crash", "trace")):
        selected_id = "log_file_explainer"
        reason = "Matched log file analysis intent (bounded read-only log tail collector)."
        suggested_inputs["log_file_path"] = extracted_path or str(DATA_DIR / "sample_system.log")

    defn = workflow_definitions.get(selected_id) or next(iter(workflow_definitions.values()))
    return {
        "ok": True,
        "prompt": clean,
        "matched_workflow_id": selected_id,
        "workflow": defn,
        "suggested_inputs": suggested_inputs,
        "planner_reasoning": reason,
    }
