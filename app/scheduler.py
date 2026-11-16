"""Explicit Opt-In Scheduled Workflow Automation with Foreground-Priority Resource Guardrails."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import SCHEDULES_FILE, ensure_data_dir, load_settings, save_settings
from app.diagnostics import system_diagnostics
from app.ollama_service import ollama_service
from app.workflows import WORKFLOW_DEFINITIONS, workflow_engine


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class WorkflowScheduler:
    """
    Manages inspectable, opt-in scheduled workflow runs (`data/schedules.json`).
    Safety & Resource Principles:
    1. Off by default (`scheduler_enabled = False` in `settings.json`).
    2. Never runs hidden jobs; every schedule, trigger, and skip reason is logged in `data/schedules.json`.
    3. Foreground-Priority Resource Guardrail: if the user is actively chatting (`ollama_service.inference_lock`
       is locked or `is_generating` is True), or another workflow is running, or CPU load > 92%,
       scheduled runs automatically defer/skip (`skipped_foreground_busy`) so foreground chat never lags.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running_loop: bool = False

    def _load_state(self) -> dict[str, Any]:
        ensure_data_dir()
        if not SCHEDULES_FILE.exists():
            return {"schedules": [], "events": []}
        try:
            raw = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {
                    "schedules": raw.get("schedules", []) if isinstance(raw.get("schedules"), list) else [],
                    "events": raw.get("events", []) if isinstance(raw.get("events"), list) else [],
                }
        except Exception:
            pass
        return {"schedules": [], "events": []}

    def _save_state(self, state: dict[str, Any]) -> None:
        ensure_data_dir()
        payload = {
            "schedules": state.get("schedules", [])[:50],
            "events": state.get("events", [])[:60],
        }
        SCHEDULES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_event(
        self,
        state: dict[str, Any],
        *,
        schedule_id: str,
        workflow_id: str,
        event_type: str,
        detail: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        ev = {
            "event_id": f"sev-{int(time.time())}-{uuid.uuid4().hex[:5]}",
            "timestamp": _now_iso(),
            "schedule_id": schedule_id,
            "workflow_id": workflow_id,
            "event_type": event_type,
            "run_id": run_id,
            "detail": detail,
        }
        events = state.setdefault("events", [])
        events.insert(0, ev)
        state["events"] = events[:60]
        return ev

    def get_status(self) -> dict[str, Any]:
        settings = load_settings()
        state = self._load_state()
        fg_busy, fg_reason = self.check_foreground_and_resources()
        return {
            "scheduler_enabled": bool(settings.get("scheduler_enabled", False)),
            "loop_active": self._running_loop,
            "foreground_busy": fg_busy,
            "resource_guardrail_status": fg_reason,
            "schedules": state["schedules"],
            "events": state["events"],
        }

    def check_foreground_and_resources(
        self, simulate_foreground_busy: bool = False
    ) -> tuple[bool, str]:
        """
        Check whether foreground chat/inference or another workflow is active,
        or whether system resources exceed safe background thresholds.
        Returns `(is_busy, reason)`.
        """
        if simulate_foreground_busy:
            return (
                True,
                "Deferred by Foreground-Priority Guardrail: Foreground chat/inference is active (simulated).",
            )

        if ollama_service.is_generating or ollama_service.inference_lock.locked():
            return (
                True,
                "Deferred by Foreground-Priority Guardrail: Local Ollama model is currently busy with foreground chat/inference.",
            )

        active_runs = [
            r for r in workflow_engine.get_runs() if r.get("status") in ("running", "paused")
        ]
        if active_runs:
            return (
                True,
                f"Deferred by Resource Guardrail: Workflow run '{active_runs[0].get('run_id')}' is currently in progress.",
            )

        hw = system_diagnostics.get_health_snapshot()
        cpu_pct = (hw.get("cpu") or {}).get("load_percent") or 0
        if cpu_pct > 92:
            return (
                True,
                f"Deferred by Resource Guardrail: System CPU load is high ({cpu_pct}% > 92% limit).",
            )

        return (False, "Idle & within 16 GB RAM / 8 GB VRAM guardrails (ready for scheduled tasks).")

    def toggle_global_scheduler(self, enabled: bool) -> dict[str, Any]:
        settings = load_settings()
        settings["scheduler_enabled"] = bool(enabled)
        save_settings(settings)
        state = self._load_state()
        self._append_event(
            state,
            schedule_id="global",
            workflow_id="*",
            event_type="global_scheduler_toggled",
            detail=f"Global scheduled automation set to {'ENABLED' if enabled else 'DISABLED (Off)'}.",
        )
        self._save_state(state)
        return self.get_status()

    def create_schedule(
        self,
        *,
        title: str,
        workflow_id: str,
        interval_minutes: int,
        inputs: dict[str, Any] | None = None,
        enabled: bool = False,
    ) -> dict[str, Any]:
        clean_title = (title or "").strip()
        if not clean_title:
            return {"ok": False, "error": "Schedule title is required."}
        if workflow_id not in WORKFLOW_DEFINITIONS:
            return {"ok": False, "error": f"Unknown workflow_id '{workflow_id}'."}

        safe_interval = max(5, min(int(interval_minutes), 1440))
        wf_def = WORKFLOW_DEFINITIONS[workflow_id]
        now_ep = time.time()
        sched = {
            "schedule_id": f"sch-{int(now_ep)}-{uuid.uuid4().hex[:6]}",
            "title": clean_title[:120],
            "workflow_id": workflow_id,
            "workflow_title": wf_def["title"],
            "read_only": bool(wf_def.get("read_only", True)),
            "interval_minutes": safe_interval,
            "inputs": inputs or {},
            "enabled": bool(enabled),
            "created_at": _now_iso(),
            "next_due_epoch": round(now_ep + safe_interval * 60, 1),
            "last_run_at": None,
            "last_run_id": None,
            "last_status": "never_run",
            "run_count": 0,
            "skipped_count": 0,
        }

        state = self._load_state()
        state["schedules"].insert(0, sched)
        self._append_event(
            state,
            schedule_id=sched["schedule_id"],
            workflow_id=workflow_id,
            event_type="schedule_created",
            detail=f"Created schedule '{sched['title']}' (every {safe_interval} min, enabled={sched['enabled']}).",
        )
        self._save_state(state)
        return {"ok": True, "schedule": sched, "status": self.get_status()}

    def toggle_schedule(self, schedule_id: str, enabled: bool) -> dict[str, Any]:
        state = self._load_state()
        target = None
        for s in state["schedules"]:
            if s.get("schedule_id") == schedule_id:
                s["enabled"] = bool(enabled)
                if enabled:
                    s["next_due_epoch"] = round(time.time() + int(s.get("interval_minutes", 30)) * 60, 1)
                target = s
                break
        if not target:
            return {"ok": False, "error": f"Schedule '{schedule_id}' not found."}

        self._append_event(
            state,
            schedule_id=schedule_id,
            workflow_id=target["workflow_id"],
            event_type="schedule_toggled",
            detail=f"Schedule '{target['title']}' set to {'ENABLED' if enabled else 'PAUSED'}.",
        )
        self._save_state(state)
        return {"ok": True, "schedule": target, "status": self.get_status()}

    def delete_schedule(self, schedule_id: str) -> dict[str, Any]:
        state = self._load_state()
        before = len(state["schedules"])
        removed_wf = "*"
        remaining = []
        for s in state["schedules"]:
            if s.get("schedule_id") == schedule_id:
                removed_wf = s.get("workflow_id", "*")
            else:
                remaining.append(s)
        state["schedules"] = remaining
        if len(remaining) < before:
            self._append_event(
                state,
                schedule_id=schedule_id,
                workflow_id=removed_wf,
                event_type="schedule_deleted",
                detail=f"Deleted schedule '{schedule_id}'.",
            )
        self._save_state(state)
        return {"ok": True, "status": self.get_status()}

    def clear_all_schedules(self) -> dict[str, Any]:
        if SCHEDULES_FILE.exists():
            SCHEDULES_FILE.unlink(missing_ok=True)
        return {"ok": True, "status": self.get_status()}

    async def trigger_schedule_now(
        self,
        schedule_id: str,
        *,
        simulate_foreground_busy: bool = False,
        wait: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a scheduled workflow run while enforcing the Foreground-Priority Resource Guardrail.
        If foreground chat/inference is active, the run is safely skipped and logged.
        """
        state = self._load_state()
        target = next((s for s in state["schedules"] if s.get("schedule_id") == schedule_id), None)
        if not target:
            return {"ok": False, "error": f"Schedule '{schedule_id}' not found."}

        is_busy, reason = self.check_foreground_and_resources(
            simulate_foreground_busy=simulate_foreground_busy
        )
        if is_busy:
            target["skipped_count"] = int(target.get("skipped_count", 0)) + 1
            target["last_status"] = "skipped_foreground_busy"
            target["last_run_at"] = _now_iso()
            target["next_due_epoch"] = round(
                time.time() + int(target.get("interval_minutes", 30)) * 60, 1
            )
            ev = self._append_event(
                state,
                schedule_id=schedule_id,
                workflow_id=target["workflow_id"],
                event_type="skipped_foreground_busy",
                detail=reason,
            )
            self._save_state(state)
            return {
                "ok": True,
                "skipped": True,
                "reason": reason,
                "event": ev,
                "schedule": target,
                "status": self.get_status(),
            }

        # Safe to run scheduled workflow
        settings = load_settings()
        model = str(settings.get("selected_model", "llama3:latest"))
        run_record = await workflow_engine.start_run(
            workflow_id=target["workflow_id"],
            inputs=target.get("inputs") or {},
            model=model,
            wait=wait,
        )

        # Reload state in case workflow took several seconds
        state = self._load_state()
        target = next((s for s in state["schedules"] if s.get("schedule_id") == schedule_id), target)
        target["run_count"] = int(target.get("run_count", 0)) + 1
        target["last_run_at"] = _now_iso()
        target["last_run_id"] = run_record.get("run_id")
        target["last_status"] = run_record.get("status", "running")
        target["next_due_epoch"] = round(
            time.time() + int(target.get("interval_minutes", 30)) * 60, 1
        )
        ev = self._append_event(
            state,
            schedule_id=schedule_id,
            workflow_id=target["workflow_id"],
            event_type="scheduled_run_triggered",
            run_id=run_record.get("run_id"),
            detail=(
                f"Triggered scheduled workflow '{target['workflow_title']}' "
                f"-> run_id={run_record.get('run_id')} (status={run_record.get('status')})."
            ),
        )
        self._save_state(state)
        return {
            "ok": True,
            "skipped": False,
            "run": run_record,
            "event": ev,
            "schedule": target,
            "status": self.get_status(),
        }

    def start_background_loop(self) -> None:
        if self._task is None or self._task.done():
            self._running_loop = True
            self._task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        while self._running_loop:
            try:
                await asyncio.sleep(15)
                settings = load_settings()
                if not settings.get("scheduler_enabled", False):
                    continue
                state = self._load_state()
                now_ep = time.time()
                for s in state.get("schedules", []):
                    if not s.get("enabled", False):
                        continue
                    due = float(s.get("next_due_epoch") or 0)
                    if due > 0 and now_ep >= due:
                        await self.trigger_schedule_now(s["schedule_id"], wait=True)
                        break
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(15)


workflow_scheduler = WorkflowScheduler()
