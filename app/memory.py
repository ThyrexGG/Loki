"""Personal & Project Memory Store for Loki (`data/memories.json`).

Memories come from two places:
- the user: added on the Memories page or by saying "remember that ..." in chat;
- Loki itself ("Learn from chats", on by default, switchable): after a chat reply, if the user's own message
  states a lasting fact about them (name, job, setup, preferences, projects), the local model extracts it and
  Loki saves it with source "auto" and tells the user right away in the chat (with Undo). Only the user's own
  words are used, never web pages, files or Loki's replies.
Everything stays on this PC; the user can edit, switch off or delete every entry.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import MEMORIES_FILE, ensure_data_dir, load_settings

CATEGORIES = ("personal", "project", "preference", "workflow")
MAX_IN_PROMPT = 12

# Cheap gate before asking the model: the message must say something about the user themself.
_SELF_FACT = re.compile(
    r"\b(i\s*'?\s*a?m\b|i\s+(work|live|use|prefer|like|love|hate|dislike|need|want|study|play|make|build|code|run|have|own)\b|"
    r"my\s+(name|job|work|pc|laptop|setup|gpu|computer|project|game|team|company|favou?rite|goal|preference|editor|language|os)\b|"
    r"call\s+me\b|i\s*'?\s*m\s+(a|an|from|working|building|making|learning)\b)", re.I)
_SKIP_LEARN = re.compile(r"^\s*(?:please\s+)?(?:always\s+)?(?:remember|save\s+to\s+memory|note\s+that|forget)\b", re.I)

LEARN_PROMPT = """You decide what a personal assistant should remember long-term about its user.
From the USER MESSAGE only, list lasting facts about the user that will still be useful in future, unrelated chats:
their name, job or studies, location (city/country only), hardware and software setup, ongoing projects, skills,
and stated preferences for how answers should be written.
Do NOT include: one-off questions or tasks, temporary moods, anything about other people, passwords, secrets,
health, money, account numbers, exact addresses or anything sensitive.
Reply with JSON only: {"facts": [{"title": "3-6 word label", "content": "one sentence in third person, e.g. The user ...", "category": "personal|project|preference|workflow"}]}
Usually there is nothing worth keeping: then reply {"facts": []}. At most 2 facts."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())} - {
        "the", "and", "for", "with", "that", "this", "user", "users", "about", "what", "how", "you", "your", "are"}


def wants_learning(text: str) -> bool:
    text = (text or "").strip()
    return 12 <= len(text) <= 2000 and bool(_SELF_FACT.search(text)) and not _SKIP_LEARN.match(text)


class MemoryStore:
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

    def _similar(self, items: list[dict[str, Any]], content: str) -> dict[str, Any] | None:
        target, t_terms = _norm(content), _terms(content)
        for it in items:
            other = it.get("content", "")
            o_terms = _terms(other)
            overlap = len(t_terms & o_terms) / max(1, len(t_terms | o_terms))
            # Same words and nearly the same text: "uses VS Code" vs "uses VS Code!", but not
            # "likes Godot" vs "likes Unity".
            if overlap >= 0.8 and difflib.SequenceMatcher(None, _norm(other), target).ratio() >= 0.85:
                return it
        return None

    def add_memory(self, title: str, content: str, category: str = "personal", source: str = "you") -> dict[str, Any]:
        clean_title = (title or "").strip()
        clean_content = (content or "").strip()
        if not clean_title or not clean_content:
            return {"ok": False, "error": "Both memory title and content are required."}
        safe_cat = category if category in CATEGORIES else "personal"
        items = self.list_memories()
        dup = self._similar(items, clean_content)
        if dup:
            # Same fact again: refresh it instead of storing a duplicate.
            dup.update(title=clean_title[:120], content=clean_content[:1200], updated_at=_now_iso())
            self._save_memories(items)
            return {"ok": True, "memory": dup, "memories": items, "duplicate": True}
        entry = {
            "memory_id": f"mem-{int(time.time())}-{uuid.uuid4().hex[:6]}",
            "category": safe_cat,
            "title": clean_title[:120],
            "content": clean_content[:1200],
            "enabled": True,
            "source": source if source in ("you", "auto") else "you",
            "created_at": _now_iso(),
        }
        items.insert(0, entry)
        self._save_memories(items)
        return {"ok": True, "memory": entry, "memories": items}

    def update_memory(self, memory_id: str, title: str | None = None, content: str | None = None,
                      category: str | None = None) -> dict[str, Any]:
        items = self.list_memories()
        for it in items:
            if it.get("memory_id") == memory_id:
                if title is not None and title.strip():
                    it["title"] = title.strip()[:120]
                if content is not None and content.strip():
                    it["content"] = content.strip()[:1200]
                if category in CATEGORIES:
                    it["category"] = category
                it["updated_at"] = _now_iso()
                self._save_memories(items)
                return {"ok": True, "memory": it, "memories": items}
        return {"ok": False, "error": f"Memory '{memory_id}' not found."}

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

    def get_active_memory_context(self, query: str = "") -> tuple[str, int]:
        """System prompt snippet of enabled memories. With many memories, preferences always go in and the rest
        are picked by how well they match the current message, so the prompt stays short."""
        settings = load_settings()
        if not settings.get("use_memories_in_chat", True):
            return ("", 0)
        enabled = [m for m in self.list_memories() if m.get("enabled", True)]
        if not enabled:
            return ("", 0)
        if len(enabled) > MAX_IN_PROMPT:
            q = _terms(query)
            prefs = [m for m in enabled if m.get("category") == "preference"][:6]
            rest = [m for m in enabled if m not in prefs]
            rest.sort(key=lambda m: -len(q & _terms(m.get("title", "") + " " + m.get("content", ""))))
            enabled = prefs + rest[: MAX_IN_PROMPT - len(prefs)]
        lines = ["WHAT YOU KNOW ABOUT THE USER (their saved memories; use when relevant, do not recite them):"]
        for m in enabled:
            lines.append(f"- [{m.get('category', 'note').upper()}] {m['title']}: {m['content']}")
        return ("\n".join(lines), len(enabled))

    async def learn_from_message(self, text: str, model: str) -> list[dict[str, Any]]:
        """Extract lasting facts from the user's own message with the local model and save them (source 'auto')."""
        settings = load_settings()
        if not settings.get("auto_learn_memories", True) or not settings.get("use_memories_in_chat", True):
            return []
        if not wants_learning(text):
            return []
        import httpx

        from app.ollama_service import apply_gentle, ollama_service

        payload: dict[str, Any] = {
            "model": model, "stream": False, "format": "json",
            "messages": [{"role": "system", "content": LEARN_PROMPT},
                         {"role": "user", "content": f"USER MESSAGE:\n<untrusted_data source=\"user\">\n{text[:2000]}\n</untrusted_data>"}],
            "options": {"temperature": 0.1, "num_ctx": 2048},
        }
        if model.startswith("qwen3"):
            payload["think"] = False
        try:
            async with ollama_service.inference_lock:
                async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0)) as client:
                    resp = await client.post(f"{ollama_service._get_base_url()}/api/chat", json=apply_gentle(payload))
            if resp.status_code != 200:
                return []
            raw = (resp.json().get("message") or {}).get("content") or ""
            facts = json.loads(raw).get("facts") or []
        except Exception:
            return []
        saved = []
        blocked = re.compile(r"password|passcode|pin\b|credit|card number|iban|ssn|social security|bank|diagnos", re.I)
        for f in facts[:2]:
            if not isinstance(f, dict):
                continue
            title, content = str(f.get("title") or "").strip(), str(f.get("content") or "").strip()
            if len(content) < 8 or blocked.search(title + " " + content):
                continue
            res = self.add_memory(title or content[:40], content, str(f.get("category") or "personal"), source="auto")
            if res.get("ok") and not res.get("duplicate"):
                saved.append(res["memory"])
        return saved


memory_store = MemoryStore()
