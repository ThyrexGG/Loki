"""Stage 4 (Task 4.1) Verification Script: Preview-and-Approval Gate & Safe New-Copy File Outputs."""

from __future__ import annotations

from pathlib import Path
import httpx
from pathlib import Path
from _isolated import base_url  # refuses to run outside tests/run_tests.py

REPO_ROOT = Path(__file__).resolve().parent.parent  # project root, wherever Loki lives



def main() -> None:
    with httpx.Client(base_url=base_url(), timeout=120.0) as c:
        # 1. Create sample messy CSV
        sc = c.post("/api/diagnostics/sample-csv").json()
        assert sc["ok"] is True
        csv_path = Path(sc["path"])
        orig_bytes = csv_path.read_bytes()
        print("1. SAMPLE MESSY CSV CREATED:", csv_path, f"({len(orig_bytes)} bytes)")

        # 2. Run `clean_csv_to_new_copy` -> must pause at `awaiting_approval` BEFORE writing
        run1 = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "clean_csv_to_new_copy",
                "inputs": {
                    "csv_file_path": str(csv_path),
                    "focus_question": "Summarize the cleaned columns and row counts in 2 short bullets.",
                },
                "wait": True,
            },
        ).json()["run"]

        assert run1["status"] == "awaiting_approval", f"Expected awaiting_approval, got {run1}"
        pa1 = run1["pending_approval"]
        target1 = Path(pa1["target_path"])
        assert not target1.exists(), "File must NOT exist on disk before user approval!"
        print("2. PAUSED AT APPROVAL GATE OK:", pa1["approval_id"])
        print("   Diff summary:", pa1["diff_summary"])
        print("   Target file exists before approval?:", target1.exists())

        # 3. Approve the pending write -> verify new copy written & original untouched
        dec1 = c.post(
            f"/api/approvals/{pa1['approval_id']}/decide",
            json={"decision": "approve"},
        ).json()
        assert dec1["ok"] is True and dec1["decision"] == "approved"
        assert target1.exists(), "Approved file must exist on disk after approval!"
        assert csv_path.read_bytes() == orig_bytes, "Original CSV file must remain untouched!"
        assert dec1["run"]["status"] == "completed"
        print("3. APPROVAL & NEW-COPY WRITE OK:", dec1["written_path"], f"({dec1['byte_size']} bytes)")
        print("   Original file untouched?:", csv_path.read_bytes() == orig_bytes)

        # 4. Run `export_research_report` and test REJECT path -> verify no file written
        # Ensure docs/ is indexed
        c.post(
            "/api/docs/folders",
            json={"folder_path": str(REPO_ROOT / "docs")},
        )
        run2 = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "export_research_report",
                "inputs": {
                    "focus_question": "Write a 3-bullet summary of Loki's privacy boundaries with citations."
                },
                "wait": True,
            },
        ).json()["run"]
        assert run2["status"] == "awaiting_approval"
        pa2 = run2["pending_approval"]
        target2 = Path(pa2["target_path"])
        assert not target2.exists()

        dec2 = c.post(
            f"/api/approvals/{pa2['approval_id']}/decide",
            json={"decision": "reject"},
        ).json()
        assert dec2["ok"] is True and dec2["decision"] == "rejected"
        assert not target2.exists(), "Rejected file must NEVER be written to disk!"
        assert dec2["run"]["status"] == "cancelled"
        print("4. REJECTION PATH OK: File not written, run status =", dec2["run"]["status"])

        # 5. Unload model from GPU VRAM after test
        un = c.post("/api/ollama/unload", json={}).json()
        print("5. VRAM UNLOADED AFTER TEST:", un["unloaded_models"])


if __name__ == "__main__":
    main()
