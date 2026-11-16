"""Stage 2 (Milestone 2 / Task 2.1) Verification Script: Workflow Engine & Read-Only PC Analyst."""

from __future__ import annotations

import httpx
from _isolated import base_url  # refuses to run outside tests/run_tests.py


def main() -> None:
    with httpx.Client(base_url=base_url(), timeout=120.0) as c:
        # 1. Verify Top Processes Collector
        procs = c.get("/api/diagnostics/processes?limit=10").json()
        assert procs["ok"] is True
        assert len(procs["processes"]) == 10
        print(
            "1. TOP PROCESSES OK:",
            len(procs["processes"]),
            "processes | Top 3:",
            [(p["name"], f"{p['memory_mb']} MB") for p in procs["processes"][:3]],
        )

        # 2. Verify Sample Log & Bounded Log Tail Reader
        s_log = c.post("/api/diagnostics/sample-log").json()
        assert s_log["ok"] is True
        sample_path = s_log["path"]
        prev = c.post(
            "/api/diagnostics/log-preview",
            json={"file_path": sample_path, "max_lines": 50},
        ).json()
        assert prev["ok"] is True
        print(
            "2. LOG PREVIEW OK:",
            prev["file_name"],
            "| Lines:",
            prev["lines_returned"],
            "| Bytes:",
            prev["total_size_bytes"],
        )

        # 3. Verify Workflow Blueprints
        wf_list = c.get("/api/workflows").json()
        def_ids = [d["id"] for d in wf_list["definitions"]]
        assert "pc_health_audit" in def_ids and "log_file_explainer" in def_ids
        print("3. WORKFLOW BLUEPRINTS OK:", def_ids)

        # 4. Verify Safe Halt on Failed Step (invalid log path stops before AI step)
        fail_run = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "pc_health_audit",
                "inputs": {"log_file_path": r"C:\nonexistent_folder\missing_file.log"},
                "wait": True,
            },
        ).json()["run"]
        assert fail_run["status"] == "failed"
        step_statuses = {s["step_id"]: s["status"] for s in fail_run["steps"]}
        assert step_statuses["inspect_selected_logs"] == "failed"
        assert step_statuses["ai_diagnostic_analysis"] == "pending"
        print("4. SAFE HALT ON STEP FAILURE OK:", fail_run["error"])
        print("   Step statuses on failure:", step_statuses)

        # 5. Verify Full End-to-End Read-Only PC Analyst Workflow (with Sample Log + WinEvents)
        ok_run = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "pc_health_audit",
                "inputs": {
                    "log_file_path": sample_path,
                    "include_windows_events": True,
                    "focus_question": "Give a very brief 3-bullet summary of RAM, GPU VRAM, and the log errors.",
                },
                "wait": True,
            },
        ).json()["run"]
        assert ok_run["status"] == "completed", f"Expected completed, got {ok_run}"
        ok_step_statuses = {s["step_id"]: s["status"] for s in ok_run["steps"]}
        print("5. FULL WORKFLOW COMPLETED:", ok_run["run_id"])
        print("   Step statuses:", ok_step_statuses)
        print("   Activity summary:", ok_run["activity_summary"])
        print("   AI Report Preview (first 300 chars):", repr((ok_run["final_output"] or "")[:300]))

        # 6. Verify Run History Persistence
        runs_after = c.get("/api/workflows").json()["runs"]
        assert len(runs_after) >= 2
        print("6. PERSISTED RUN HISTORY COUNT:", len(runs_after))

        # 7. Free GPU VRAM after test
        un = c.post("/api/ollama/unload", json={}).json()
        print("7. VRAM UNLOADED AFTER TEST:", un["unloaded_models"])


if __name__ == "__main__":
    main()
