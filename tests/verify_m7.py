"""Stage 7 / Task 7.1 Verification Script for Loki:
Explicit Opt-In Scheduled Workflow Automation & Foreground-Priority Resource Guardrails.
"""

import sys
import httpx
from _isolated import base_url  # refuses to run outside tests/run_tests.py

BASE_URL = base_url()


def main() -> int:
    print("=== Loki Stage 7 Verification (Opt-In Scheduled Automation & Guardrails) ===")
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        # 1. Reset scheduler to OFF & clear schedules
        client.post("/api/schedules/global", json={"enabled": False})
        client.delete("/api/schedules")

        r_st = client.get("/api/schedules")
        assert r_st.status_code == 200
        st = r_st.json()
        print(
            f"[1] Default Scheduler State: scheduler_enabled={st['scheduler_enabled']} | "
            f"loop_active={st['loop_active']} | "
            f"foreground_busy={st['foreground_busy']} | "
            f"guardrail='{st['resource_guardrail_status']}'"
        )
        assert st["scheduler_enabled"] is False
        assert st["loop_active"] is True

        # 2. Create a read-only scheduled job (paused by default)
        r_cr = client.post(
            "/api/schedules",
            json={
                "title": "Hourly PC Health Check",
                "workflow_id": "pc_health_audit",
                "interval_minutes": 60,
                "inputs": {
                    "include_windows_events": False,
                    "focus_question": "Give a brief 2-sentence summary of CPU, RAM, and GPU VRAM headroom.",
                },
                "enabled": False,
            },
        )
        assert r_cr.status_code == 200
        cr_data = r_cr.json()
        assert cr_data["ok"] is True
        sch = cr_data["schedule"]
        sch_id = sch["schedule_id"]
        print(
            f"[2] Created schedule id={sch_id} | title='{sch['title']}' | "
            f"workflow={sch['workflow_id']} | interval={sch['interval_minutes']}m | enabled={sch['enabled']}"
        )
        assert sch["enabled"] is False

        # 3. Test Foreground-Priority Resource Guardrail (simulate foreground chat active)
        r_skip = client.post(
            f"/api/schedules/{sch_id}/run-now",
            json={"simulate_foreground_busy": True, "wait": True},
        )
        assert r_skip.status_code == 200
        skip_data = r_skip.json()
        print(
            f"[3] Guardrail Deferral Check: skipped={skip_data['skipped']} | "
            f"skipped_count={skip_data['schedule']['skipped_count']} | "
            f"last_status={skip_data['schedule']['last_status']} | "
            f"reason='{skip_data['reason']}'"
        )
        assert skip_data["skipped"] is True
        assert skip_data["schedule"]["skipped_count"] == 1
        assert skip_data["schedule"]["last_status"] == "skipped_foreground_busy"

        # 4. Trigger live scheduled execution when foreground is idle
        print("[4] Triggering scheduled pc_health_audit run while foreground is idle...")
        r_run = client.post(
            f"/api/schedules/{sch_id}/run-now",
            json={"simulate_foreground_busy": False, "wait": True},
        )
        assert r_run.status_code == 200
        run_data = r_run.json()
        assert run_data["skipped"] is False
        wf_run = run_data["run"]
        print(
            f"    -> Scheduled Run Completed: run_id={wf_run['run_id']} | "
            f"status={wf_run['status']} | "
            f"run_count={run_data['schedule']['run_count']} | "
            f"skipped_count={run_data['schedule']['skipped_count']}"
        )
        assert wf_run["status"] == "completed"
        assert run_data["schedule"]["run_count"] == 1
        assert run_data["schedule"]["skipped_count"] == 1

        # 5. Verify scheduler audit events log
        events = run_data["status"]["events"]
        event_types = [e["event_type"] for e in events]
        print(f"[5] Scheduler Audit Log Events ({len(events)}): {event_types}")
        assert "scheduled_run_triggered" in event_types
        assert "skipped_foreground_busy" in event_types
        assert "schedule_created" in event_types

        # 6. Verify global switch stays OFF by default and clean up test schedule
        client.delete(f"/api/schedules/{sch_id}")
        client.post("/api/schedules/global", json={"enabled": False})

        # 7. Unload model from VRAM
        r_un = client.post("/api/ollama/unload", json={"model": "llama3:latest"})
        assert r_un.status_code == 200
        print(f"[6] Unloaded llama3:latest from VRAM: {r_un.json()['unloaded_models']}")

    print("=== ALL STAGE 7 CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
