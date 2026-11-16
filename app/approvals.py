"""Preview-and-Approval Gate & Safe New-Copy File Writer for Loki (Stage 4)."""

from __future__ import annotations

import io
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import (
    DATA_DIR,
    EXPORTS_DIR,
    PENDING_APPROVALS_FILE,
    ensure_data_dir,
    load_workflow_runs,
    save_workflow_runs,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_sample_messy_csv() -> dict[str, Any]:
    """Create a sample messy CSV inside loki/data/sample_messy_tasks.csv for one-click testing."""
    ensure_data_dir()
    sample_csv = DATA_DIR / "sample_messy_tasks.csv"
    content = (
        "  Task Title  , Owner Name , Priority Level , Estimated Hours , Status \n"
        "  Audit GPU VRAM usage , Alice  , High , 2.5 , Completed \n"
        "  Index project docs , Bob , Medium , 1.5 , In Progress \n"
        " , , , , \n"
        "  Index project docs , Bob , Medium , 1.5 , In Progress \n"
        "  Prepare release notes ,   Charlie , Low , 3.0 , Pending \n"
        "  Verify localhost CSP , Alice , High , 1.0 , Completed \n"
        " , , , , \n"
    )
    sample_csv.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": str(sample_csv.resolve()),
        "size_bytes": len(content.encode("utf-8")),
    }


def clean_csv_deterministic(file_path: str) -> dict[str, Any]:
    """
    Deterministically read a user-specified .csv file (read-only), normalize column headers,
    strip whitespace, drop empty and duplicate rows, and return a before/after diff + cleaned CSV string.
    """
    raw = (file_path or "").strip().strip('"').strip("'")
    if not raw:
        return {"ok": False, "error": "CSV file path is required."}

    target = Path(raw)
    try:
        resolved = target.resolve()
    except Exception as exc:
        return {"ok": False, "error": f"Invalid file path '{raw}': {exc}"}

    if not resolved.exists() or not resolved.is_file():
        return {"ok": False, "error": f"CSV file does not exist: {resolved}"}
    if resolved.suffix.lower() != ".csv":
        return {"ok": False, "error": f"File must have a .csv extension (got '{resolved.suffix}')."}

    try:
        df_raw = pd.read_csv(resolved, dtype=str, keep_default_na=False)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to parse CSV '{resolved.name}': {exc}"}

    rows_before = len(df_raw)
    orig_cols = list(df_raw.columns)

    # 1. Normalize column headers (strip + snake_case)
    new_cols = []
    renamed_pairs = []
    for c in orig_cols:
        cleaned_c = re.sub(r"[^a-zA-Z0-9]+", "_", str(c).strip()).strip("_").lower()
        if not cleaned_c:
            cleaned_c = "col"
        new_cols.append(cleaned_c)
        if cleaned_c != c:
            renamed_pairs.append(f"'{c}' -> '{cleaned_c}'")

    df = df_raw.copy()
    df.columns = new_cols

    # 2. Trim whitespace in all string cells
    for col in df.columns:
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    # 3. Drop completely empty rows
    non_empty_mask = df.apply(lambda row: any(bool(str(val).strip()) for val in row), axis=1)
    df_non_empty = df[non_empty_mask].reset_index(drop=True)
    empty_removed = rows_before - len(df_non_empty)

    # 4. Drop exact duplicate rows
    df_clean = df_non_empty.drop_duplicates().reset_index(drop=True)
    duplicates_removed = len(df_non_empty) - len(df_clean)
    rows_after = len(df_clean)

    if rows_after == 0:
        return {"ok": False, "error": "Cleaned CSV resulted in 0 valid rows; refusing to export empty table."}

    out_buf = io.StringIO()
    df_clean.to_csv(out_buf, index=False, lineterminator="\n")
    cleaned_csv_text = out_buf.getvalue()

    diff_summary = (
        f"Source: {resolved.name} | Rows: {rows_before} -> {rows_after} "
        f"(removed {empty_removed} empty row(s) and {duplicates_removed} duplicate row(s)) | "
        f"Normalized {len(renamed_pairs)} column header(s): {', '.join(renamed_pairs[:6])}"
    )

    return {
        "ok": True,
        "source_path": str(resolved),
        "source_name": resolved.name,
        "stem": resolved.stem,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "empty_removed": empty_removed,
        "duplicates_removed": duplicates_removed,
        "columns_before": orig_cols,
        "columns_after": new_cols,
        "diff_summary": diff_summary,
        "cleaned_csv": cleaned_csv_text,
        "sample_rows": df_clean.head(10).to_dict(orient="records"),
    }


class ApprovalManager:
    """
    Enforces Loki's Preview-and-Approval Gate before any workflow can write an output file.
    - Never overwrites existing files.
    - Never modifies or deletes original user files.
    - Writes exclusively to new copies inside `loki/data/exports/`.
    """

    def _load_all(self) -> list[dict[str, Any]]:
        ensure_data_dir()
        if not PENDING_APPROVALS_FILE.exists():
            return []
        try:
            data = json.loads(PENDING_APPROVALS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_all(self, items: list[dict[str, Any]]) -> None:
        ensure_data_dir()
        PENDING_APPROVALS_FILE.write_text(json.dumps(items[:50], indent=2), encoding="utf-8")

    def list_approvals(self) -> list[dict[str, Any]]:
        """Return all approval requests (without duplicating large full_content in list view)."""
        items = self._load_all()
        return items

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        for item in self._load_all():
            if item.get("approval_id") == approval_id:
                return item
        return None

    def _allocate_safe_export_path(self, filename: str) -> Path:
        """Return a guaranteed non-existing path inside `loki/data/exports/`."""
        ensure_data_dir()
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", filename).strip("_")
        if not safe_name:
            safe_name = f"output_{int(time.time())}.txt"
        candidate = (EXPORTS_DIR / safe_name).resolve()
        if EXPORTS_DIR.resolve() not in candidate.parents:
            raise ValueError("Target path must be inside loki/data/exports/.")
        counter = 1
        stem = candidate.stem
        suffix = candidate.suffix
        while candidate.exists():
            candidate = (EXPORTS_DIR / f"{stem}_{counter}{suffix}").resolve()
            counter += 1
        return candidate

    def create_write_approval(
        self,
        run_id: str,
        workflow_id: str,
        workflow_title: str,
        step_id: str,
        step_title: str,
        suggested_filename: str,
        source_description: str,
        diff_summary: str,
        full_content: str,
    ) -> dict[str, Any]:
        """Create a pending approval record for writing a new output copy."""
        target_path = self._allocate_safe_export_path(suggested_filename)
        approval_id = f"apr-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        preview_lines = full_content.splitlines()[:60]
        preview_text = "\n".join(preview_lines)
        if len(full_content.splitlines()) > 60:
            preview_text += "\n... (truncated in preview)"

        record = {
            "approval_id": approval_id,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "workflow_title": workflow_title,
            "step_id": step_id,
            "step_title": step_title,
            "action_type": "write_new_copy",
            "source_description": source_description,
            "target_path": str(target_path),
            "target_filename": target_path.name,
            "diff_summary": diff_summary,
            "preview_content": preview_text,
            "full_content": full_content,
            "byte_size": len(full_content.encode("utf-8")),
            "status": "pending",
            "created_at": _now_iso(),
            "decided_at": None,
        }
        items = self._load_all()
        items.insert(0, record)
        self._save_all(items)
        return record

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        """
        Approve or reject a pending file-write request and update the associated workflow run.
        `decision` must be `'approve'` or `'reject'`.
        """
        items = self._load_all()
        target_item: dict[str, Any] | None = None
        for it in items:
            if it.get("approval_id") == approval_id:
                target_item = it
                break

        if not target_item:
            return {"ok": False, "error": f"Approval '{approval_id}' not found."}
        if target_item.get("status") != "pending":
            return {
                "ok": False,
                "error": f"Approval '{approval_id}' has already been {target_item.get('status')}.",
            }

        now = _now_iso()
        run_id = target_item.get("run_id", "")
        step_id = target_item.get("step_id", "")

        if decision == "approve":
            # Verify destination is inside EXPORTS_DIR and does not overwrite an existing file
            dest = Path(target_item["target_path"]).resolve()
            if EXPORTS_DIR.resolve() not in dest.parents:
                return {"ok": False, "error": "Blocked: Target path is outside loki/data/exports/."}
            if dest.exists():
                dest = self._allocate_safe_export_path(dest.name)
                target_item["target_path"] = str(dest)
                target_item["target_filename"] = dest.name

            content_str = str(target_item.get("full_content", ""))
            dest.write_text(content_str, encoding="utf-8")

            target_item["status"] = "approved"
            target_item["decided_at"] = now
            self._save_all(items)

            # Update associated workflow run
            runs = load_workflow_runs()
            updated_run = None
            for r in runs:
                if r.get("run_id") == run_id:
                    r["status"] = "completed"
                    r["finished_at"] = now
                    r["approved_output_path"] = str(dest)
                    for st in r.get("steps", []):
                        if st.get("step_id") == step_id:
                            st["status"] = "completed"
                            st["finished_at"] = now
                            st["summary"] = (
                                f"Approved by user -> wrote new copy ({target_item['byte_size']} bytes) "
                                f"to {dest}"
                            )
                    updated_run = r
                    break
            save_workflow_runs(runs)
            return {
                "ok": True,
                "decision": "approved",
                "written_path": str(dest),
                "byte_size": target_item["byte_size"],
                "approval": target_item,
                "run": updated_run,
            }

        elif decision == "reject":
            target_item["status"] = "rejected"
            target_item["decided_at"] = now
            self._save_all(items)

            runs = load_workflow_runs()
            updated_run = None
            for r in runs:
                if r.get("run_id") == run_id:
                    r["status"] = "cancelled"
                    r["finished_at"] = now
                    r["error"] = "Write approval rejected by user — no output file was created."
                    for st in r.get("steps", []):
                        if st.get("step_id") == step_id:
                            st["status"] = "cancelled"
                            st["finished_at"] = now
                            st["summary"] = "Rejected by user — no file was written to disk."
                    updated_run = r
                    break
            save_workflow_runs(runs)
            return {
                "ok": True,
                "decision": "rejected",
                "written_path": None,
                "approval": target_item,
                "run": updated_run,
            }

        return {"ok": False, "error": f"Invalid decision '{decision}'."}


approval_manager = ApprovalManager()
