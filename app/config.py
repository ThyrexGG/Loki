"""Configuration, privacy boundaries, and local storage management for Loki."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_data_dir() -> Path:
    """`data/` in the project, unless LOKI_DATA_DIR points elsewhere (used by tests/run_tests.py
    so verification runs never touch the user's real chats, memories, index or settings)."""
    override = os.environ.get("LOKI_DATA_DIR", "").strip()
    if not override:
        return BASE_DIR / "data"
    path = Path(override)
    if not path.is_absolute():
        raise ValueError("LOKI_DATA_DIR must be an absolute path.")
    return path.resolve()


DATA_DIR = _resolve_data_dir()
STATIC_DIR = BASE_DIR / "static"

SETTINGS_FILE = DATA_DIR / "settings.json"
CONVERSATIONS_FILE = DATA_DIR / "conversations.json"
WORKFLOW_RUNS_FILE = DATA_DIR / "workflow_runs.json"
PENDING_APPROVALS_FILE = DATA_DIR / "pending_approvals.json"
MEMORIES_FILE = DATA_DIR / "memories.json"
ACTIVITY_LEDGER_FILE = DATA_DIR / "activity_ledger.json"
SCHEDULES_FILE = DATA_DIR / "schedules.json"
EXPORTS_DIR = DATA_DIR / "exports"
INDEX_DB_FILE = DATA_DIR / "index.db"

# Strict localhost defaults — never expose Loki or Ollama to public interfaces
LOKI_HOST = "127.0.0.1"
LOKI_PORT = 8420
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_EXE_PATH = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "Ollama" / "ollama.exe"
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "ollama_base_url": DEFAULT_OLLAMA_BASE_URL,
    "selected_model": "gemma2:9b",
    "num_ctx": 4096,  # Safe default for 8 GB VRAM (RTX 5050 Laptop GPU)
    "temperature": 0.3,
    "save_chat_history": True,
    "use_memories_in_chat": True,
    "auto_model_routing": True,  # pick a specialist model per task (ADR-010)
    "web_access": True,  # search the web / read pasted links automatically (ADR-011)
    "selected_tts_voice": "Microsoft Zira Desktop",
    "cloud_global_opt_in": False,  # Hard-off by default
    "cloud_providers": {
        "openai": {
            "enabled": False,
            "display_name": "ChatGPT (OpenAI API)",
            "default_model": "gpt-4o-mini",
            "env_var": "OPENAI_API_KEY",
        },
        "anthropic": {
            "enabled": False,
            "display_name": "Claude (Anthropic API)",
            "default_model": "claude-3-5-haiku-latest",
            "env_var": "ANTHROPIC_API_KEY",
        },
        "gemini": {
            "enabled": False,
            "display_name": "Gemini (Google API)",
            "default_model": "gemini-2.5-flash",
            "env_var": "GEMINI_API_KEY",
        },
    },
    "indexed_folders": [],
    "indexing_paused": False,
    "scheduler_enabled": False,  # Scheduled automation is off by default
}


def ensure_data_dir() -> None:
    """Ensure the local data and exports directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, Any]:
    """Load settings from disk, falling back to safe local-only defaults."""
    ensure_data_dir()
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SETTINGS)
        merged.update(raw)
        # Always enforce localhost URL safety check for Ollama
        if not str(merged.get("ollama_base_url", "")).startswith(
            ("http://127.0.0.1", "http://localhost")
        ):
            merged["ollama_base_url"] = DEFAULT_OLLAMA_BASE_URL
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Persist non-sensitive user settings to data/settings.json."""
    ensure_data_dir()
    # Enforce localhost-only Ollama URL
    if not str(settings.get("ollama_base_url", "")).startswith(
        ("http://127.0.0.1", "http://localhost")
    ):
        raise ValueError("For privacy, Ollama URL must be bound to localhost (127.0.0.1).")
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings


# ---------------------------------------------------------------------------
# Multi-chat store (data/conversations.json, format v2):
#   {"version": 2, "chats": [{"id", "title", "created", "updated", "messages": [...]}]}
# The legacy v1 file (a bare list of messages) is migrated into a single chat on first read.
# ---------------------------------------------------------------------------
CHAT_TITLE_MAX = 60


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")


def derive_chat_title(messages: list[dict[str, Any]]) -> str:
    """Title a chat from its first user message (single line, truncated)."""
    for m in messages:
        if m.get("role") == "user" and str(m.get("content", "")).strip():
            text = " ".join(str(m["content"]).split())
            return text if len(text) <= CHAT_TITLE_MAX else text[: CHAT_TITLE_MAX - 1].rstrip() + "…"
    return "New chat"


def load_chat_store() -> dict[str, Any]:
    """Load all saved chats, migrating the legacy single-conversation list if present."""
    ensure_data_dir()
    empty: dict[str, Any] = {"version": 2, "chats": []}
    if not CONVERSATIONS_FILE.exists():
        return empty
    try:
        data = json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if isinstance(data, list):  # v1: one implicit conversation
        if not data:
            return empty
        # Stable id + timestamp so repeated reads agree until the store is first saved as v2.
        import hashlib
        from datetime import datetime
        legacy_id = "legacy" + hashlib.sha1(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()[:12]
        ts = datetime.fromtimestamp(CONVERSATIONS_FILE.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        return {"version": 2, "chats": [{
            "id": legacy_id, "title": derive_chat_title(data),
            "created": ts, "updated": ts, "messages": data,
        }]}
    if isinstance(data, dict) and isinstance(data.get("chats"), list):
        data["chats"] = [c for c in data["chats"] if isinstance(c, dict) and c.get("id")]
        return data
    return empty


def save_chat_store(store: dict[str, Any]) -> None:
    ensure_data_dir()
    store["version"] = 2
    CONVERSATIONS_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def list_chats() -> list[dict[str, Any]]:
    """Chat summaries, most recently updated first."""
    chats = load_chat_store()["chats"]
    summaries = [({
        "id": c["id"], "title": c.get("title") or derive_chat_title(c.get("messages", [])),
        "created": c.get("created"), "updated": c.get("updated"),
        "message_count": len(c.get("messages", [])),
    }, i) for i, c in enumerate(chats)]
    # Newest first; on equal timestamps (same second) the later-stored chat wins.
    summaries.sort(key=lambda si: (si[0].get("updated") or "", si[1]), reverse=True)
    return [s for s, _ in summaries]


def get_chat(chat_id: str) -> dict[str, Any] | None:
    return next((c for c in load_chat_store()["chats"] if c["id"] == chat_id), None)


def upsert_chat(chat_id: str, messages: list[dict[str, Any]], title: str | None = None) -> dict[str, Any]:
    """Create or replace a chat's messages. Title is derived unless the user renamed it."""
    store = load_chat_store()
    chat = next((c for c in store["chats"] if c["id"] == chat_id), None)
    ts = _now_iso()
    if chat is None:
        chat = {"id": chat_id, "created": ts, "title_custom": False}
        store["chats"].append(chat)
    # Screenshots are never written to disk: keep a note instead of the image (ADR-013).
    cleaned = []
    for m in messages:
        if isinstance(m, dict) and m.get("images"):
            m = {k: v for k, v in m.items() if k != "images"}
            m["had_screenshot"] = True
        if isinstance(m, dict) and isinstance(m.get("attached_file"), dict) and "content" in m["attached_file"]:
            af = dict(m["attached_file"])
            af.pop("content", None)
            m = {**m, "attached_file": af}
        cleaned.append(m)
    messages = cleaned
    chat["messages"] = messages
    chat["updated"] = ts
    if title:
        chat["title"] = title.strip()[:CHAT_TITLE_MAX]
        chat["title_custom"] = True
    elif not chat.get("title_custom"):
        chat["title"] = derive_chat_title(messages)
    save_chat_store(store)
    return chat


def rename_chat(chat_id: str, title: str) -> dict[str, Any] | None:
    store = load_chat_store()
    chat = next((c for c in store["chats"] if c["id"] == chat_id), None)
    if chat is None:
        return None
    chat["title"] = " ".join(title.split())[:CHAT_TITLE_MAX] or derive_chat_title(chat.get("messages", []))
    chat["title_custom"] = True
    save_chat_store(store)
    return chat


def delete_chat(chat_id: str) -> bool:
    store = load_chat_store()
    before = len(store["chats"])
    store["chats"] = [c for c in store["chats"] if c["id"] != chat_id]
    if len(store["chats"]) == before:
        return False
    if store["chats"]:
        save_chat_store(store)
    else:
        clear_conversations()
    return True


def load_conversations() -> list[dict[str, Any]]:
    """Legacy API: messages of the most recently updated chat."""
    chats = list_chats()
    if not chats:
        return []
    chat = get_chat(chats[0]["id"])
    return chat.get("messages", []) if chat else []


def save_conversations(messages: list[dict[str, Any]]) -> None:
    """Legacy API: replace the most recently updated chat (or create one)."""
    import uuid
    chats = list_chats()
    upsert_chat(chats[0]["id"] if chats else uuid.uuid4().hex, messages)


def clear_conversations() -> None:
    """Delete stored conversation history."""
    if CONVERSATIONS_FILE.exists():
        CONVERSATIONS_FILE.unlink()


def load_workflow_runs() -> list[dict[str, Any]]:
    """Load persisted workflow run history from data/workflow_runs.json."""
    ensure_data_dir()
    if not WORKFLOW_RUNS_FILE.exists():
        return []
    try:
        data = json.loads(WORKFLOW_RUNS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_workflow_runs(runs: list[dict[str, Any]]) -> None:
    """Persist workflow run history (capped at most recent 50 runs)."""
    ensure_data_dir()
    capped = runs[:50]
    WORKFLOW_RUNS_FILE.write_text(json.dumps(capped, indent=2), encoding="utf-8")


def clear_workflow_runs() -> None:
    """Delete stored workflow run history."""
    if WORKFLOW_RUNS_FILE.exists():
        WORKFLOW_RUNS_FILE.unlink()


def inspect_stored_data() -> dict[str, Any]:
    """Return an inspectable manifest of all files currently stored in loki/data/."""
    ensure_data_dir()
    files_info = []
    total_bytes = 0
    for item in sorted(DATA_DIR.rglob("*")):
        if item.is_file():
            size = item.stat().st_size
            total_bytes += size
            files_info.append(
                {
                    "name": item.name,
                    # e.g. "data\\index.db"; relative to DATA_DIR's parent so LOKI_DATA_DIR outside the project works
                    "relative_path": str(item.relative_to(DATA_DIR.parent)),
                    "absolute_path": str(item.resolve()),
                    "size_bytes": size,
                }
            )
    return {
        "data_directory": str(DATA_DIR.resolve()),
        "ollama_models_directory": r"D:\OllamaModels",
        "total_files": len(files_info),
        "total_bytes": total_bytes,
        "files": files_info,
    }


def wipe_all_data() -> dict[str, Any]:
    """Delete all stored Loki files inside loki/data/ and reset to clean state."""
    ensure_data_dir()
    removed = []
    for item in sorted(DATA_DIR.rglob("*"), reverse=True):
        if item.is_file():
            removed.append(str(item.name))
            item.unlink(missing_ok=True)
    return {"removed_files": removed, "data_directory": str(DATA_DIR.resolve())}


def web_access_enabled(settings: dict[str, Any] | None = None) -> bool:
    """Web access setting; LOKI_WEB_ACCESS=0 forces it off (the isolated test runner sets this)."""
    if os.environ.get("LOKI_WEB_ACCESS", "").strip() == "0":
        return False
    settings = settings if settings is not None else load_settings()
    return bool(settings.get("web_access", True))

