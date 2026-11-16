"""User-controlled Personal & Project Memory Store for Loki (`data/memories.json`)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import MEMORIES_FILE, ensure_data_dir, load_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class MemoryStore:
    """
    Stores explicit personal/project notes and preferences that the user chooses to give Loki.
    - Memories are never extracted silently; the user adds, toggles, or deletes every entry.
    - Stored in `loki/data/memories.json`.
    """

    def list_memories(self) -> list[dict[str, Any]]:
        ensure_data_dir()
        if not MEMORIES_FILE.exists():
            return []
        try:
            data = json.loads(MEMORIES_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_memories(self, items: list[dict[str, Any]]) -> None:
        ensure_data_dir()
        MEMORIES_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def add_memory(self, title: str, content: str, category: str = "personal") -> dict[str, Any]:
        clean_title = (title or "").strip()
        clean_content = (content or "").strip()
        if not clean_title or not clean_content:
            return {"ok": False, "error": "Both memory title and content are required."}

        safe_cat = category if category in ("personal", "project", "preference", "workflow") else "personal"
        entry = {
            "memory_id": f"mem-{int(time.time())}-{uuid.uuid4().hex[:6]}",
            "category": safe_cat,
            "title": clean_title[:120],
            "content": clean_content[:1200],
            "enabled": True,
            "created_at": _now_iso(),
        }
        items = self.list_memories()
        items.insert(0, entry)
        self._save_memories(items)
        return {"ok": True, "memory": entry, "memories": items}

    def toggle_memory(self, memory_id: str, enabled: bool) -> dict[str, Any]:
        items = self.list_memories()
        found = False
        for it in items:
            if it.get("memory_id") == memory_id:
                it["enabled"] = bool(enabled)
                found = True
                break
        if not found:
            return {"ok": False, "error": f"Memory '{memory_id}' not found."}
        self._save_memories(items)
        return {"ok": True, "memories": items}

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        items = [m for m in self.list_memories() if m.get("memory_id") != memory_id]
        self._save_memories(items)
        return {"ok": True, "memories": items}

    def clear_all(self) -> dict[str, Any]:
        if MEMORIES_FILE.exists():
            MEMORIES_FILE.unlink(missing_ok=True)
        return {"ok": True, "memories": []}

    def get_active_memory_context(self) -> tuple[str, int]:
        """Return formatted system prompt snippet of enabled memories and the count used."""
        settings = load_settings()
        if not settings.get("use_memories_in_chat", True):
            return ("", 0)
        enabled = [m for m in self.list_memories() if m.get("enabled", True)]
        if not enabled:
            return ("", 0)

        lines = [
            "USER-APPROVED PERSONAL & PROJECT CONTEXT (explicitly provided by the user):",
        ]
        for m in enabled:
            lines.append(f"- [{m.get('category', 'note').upper()}] {m['title']}: {m['content']}")
        return ("\n".join(lines), len(enabled))


memory_store = MemoryStore()
