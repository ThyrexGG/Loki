"""Stage 8 / Task 8.1 Verification Script for Loki:
Natural-Language Job-to-Workflow Planner & Domain Workflows
(game_dev_project_audit, folder_organization_plan, content_publishing_kit).
"""

from pathlib import Path
import json
import sys
import httpx
from pathlib import Path
from _isolated import base_url, test_data_dir  # refuses to run outside tests/run_tests.py

REPO_ROOT = Path(__file__).resolve().parent.parent  # project root, wherever Loki lives


BASE_URL = base_url()


def main() -> int:
    print("=== Loki Stage 8 Verification (gemma2:9b Upgrade, NL Planner & Domain Workflows) ===")
    with httpx.Client(base_url=BASE_URL, timeout=180.0) as client:
        # 0. Verify gemma2:9b (9.2B) is installed and select it as default model
        client.post("/api/settings", json={"selected_model": "gemma2:9b"})
        r_st = client.get("/api/status")
        assert r_st.status_code == 200
        st_data = r_st.json()
        installed = [m["name"] for m in st_data["ollama"]["installed_models"]]
        print(f"[0] Installed Local Ollama Models: {installed} | Active Default: {st_data['settings']['selected_model']}")
        assert "gemma2:9b" in installed

        # Stream a test prompt on gemma2:9b and inspect VRAM & speed
        reply_gemma = ""
        tok_s = None
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "In one short sentence, state your model family and that you are running locally on Loki."}],
                "model": "gemma2:9b",
                "provider": "ollama",
                "save_history": False,
            },
        ) as stream:
            for line in stream.iter_lines():
                if not line:
                    continue
                pkt = json.loads(line)
                if pkt.get("type") == "token":
                    reply_gemma += pkt.get("content", "")
                elif pkt.get("type") == "done":
                    tok_s = pkt.get("tokens_per_sec")
        st_loaded = client.get("/api/status").json()
        running_m = st_loaded["ollama"]["running_models"]
        print(f"    -> gemma2:9b Reply ({tok_s} tok/s): {reply_gemma.strip()}")
        print(f"    -> RTX 5050 VRAM Status while gemma2:9b loaded: {running_m}")
        assert len(reply_gemma.strip()) > 5

        # 1. Verify all 8 workflow definitions are registered
        r_wf = client.get("/api/workflows")
        assert r_wf.status_code == 200
        defs = r_wf.json()["definitions"]
        wf_ids = [d["id"] for d in defs]
        print(f"[1] Registered Workflows ({len(wf_ids)}): {wf_ids}")
        for expected in (
            "pc_health_audit",
            "log_file_explainer",
            "folder_research_digest",
            "clean_csv_to_new_copy",
            "export_research_report",
            "game_dev_project_audit",
            "folder_organization_plan",
            "content_publishing_kit",
        ):
            assert expected in wf_ids, f"Missing workflow: {expected}"

        # 2. Verify Natural-Language Job Planner across 4 everyday prompts
        prompts_and_targets = [
            (
                f"Scan my game project folder at {REPO_ROOT} and write a build report",
                "game_dev_project_audit",
            ),
            (
                f"Organize messy files in {test_data_dir()} and create a folder plan",
                "folder_organization_plan",
            ),
            (
                "Prepare a YouTube video publishing kit and chapter timestamps about Loki",
                "content_publishing_kit",
            ),
            (
                "Clean up duplicate rows in my messy CSV spreadsheet",
                "clean_csv_to_new_copy",
            ),
        ]
        for prompt_text, expected_wf in prompts_and_targets:
            r_pl = client.post("/api/workflows/plan", json={"prompt": prompt_text})
            assert r_pl.status_code == 200
            pl = r_pl.json()
            assert pl["matched_workflow_id"] == expected_wf, (
                f"Expected {expected_wf}, got {pl['matched_workflow_id']}"
            )
            print(
                f"[2] NL Planner: '{prompt_text[:52]}...' -> {pl['matched_workflow_id']} "
                f"({pl['planner_reasoning']})"
            )

        # 3. Run game_dev_project_audit on the Loki project folder
        print(f"[3] Running game_dev_project_audit workflow on {REPO_ROOT}...")
        r_run1 = client.post(
            "/api/workflows/run",
            json={
                "workflow_id": "game_dev_project_audit",
                "inputs": {
                    "project_folder_path": str(REPO_ROOT),
                    "focus_question": "Give a concise 3-bullet build & asset summary.",
                },
                "wait": True,
            },
        )
        assert r_run1.status_code == 200
        run1 = r_run1.json()["run"]
        print(
            f"    -> Run {run1['run_id']} paused at status={run1['status']} | "
            f"step1='{run1['steps'][0]['summary']}'"
        )
        assert run1["status"] == "awaiting_approval"
        apr1_id = run1["pending_approval"]["approval_id"]

        r_dec1 = client.post(
            f"/api/approvals/{apr1_id}/decide",
            json={"decision": "approve"},
        )
        assert r_dec1.status_code == 200
        dec1 = r_dec1.json()
        assert dec1["ok"] is True
        written1 = Path(dec1["written_path"])
        assert written1.exists() and written1.stat().st_size > 100
        print(f"    -> Approved & saved build report to: {written1} ({written1.stat().st_size} B)")

        # 4. Run folder_organization_plan on the isolated test data folder
        print(f"[4] Running folder_organization_plan workflow on {test_data_dir()}...")
        r_run2 = client.post(
            "/api/workflows/run",
            json={
                "workflow_id": "folder_organization_plan",
                "inputs": {
                    "target_folder_path": str(test_data_dir()),
                    "focus_question": "Summarize the proposed category folders in 3 short bullets.",
                },
                "wait": True,
            },
        )
        assert r_run2.status_code == 200
        run2 = r_run2.json()["run"]
        print(
            f"    -> Run {run2['run_id']} paused at status={run2['status']} | "
            f"step1='{run2['steps'][0]['summary']}'"
        )
        assert run2["status"] == "awaiting_approval"
        apr2_id = run2["pending_approval"]["approval_id"]

        r_dec2 = client.post(
            f"/api/approvals/{apr2_id}/decide",
            json={"decision": "approve"},
        )
        assert r_dec2.status_code == 200
        dec2 = r_dec2.json()
        assert dec2["ok"] is True
        written2 = Path(dec2["written_path"])
        assert written2.exists() and written2.stat().st_size > 100
        print(f"    -> Approved & saved organization plan to: {written2} ({written2.stat().st_size} B)")

        # 5. Unload active models from VRAM
        r_un = client.post("/api/ollama/unload", json={})
        assert r_un.status_code == 200
        print(f"[5] Unloaded models from RTX 5050 VRAM: {r_un.json()['unloaded_models']}")

    print("=== ALL STAGE 8 CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
