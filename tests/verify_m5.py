"""Stage 5 / Task 5.1 Verification Script for Loki:
Personal/Project Memory Store & Local Push-to-Talk Voice Interface.
"""

import json
import sys
import httpx
from _isolated import base_url  # refuses to run outside tests/run_tests.py

BASE_URL = base_url()


def main() -> int:
    print("=== Loki Stage 5 Verification (Memory Store & Local Voice) ===")
    with httpx.Client(base_url=BASE_URL, timeout=90.0) as client:
        # 1. Verify Local Voice Status & Privacy Boundaries
        r_voice = client.get("/api/voice/status")
        assert r_voice.status_code == 200, f"Voice status failed: {r_voice.text}"
        vdata = r_voice.json()
        print(
            f"[1] Local Voice Recognizer: {vdata['recognizer_engine']} | "
            f"TTS Engine: {vdata['tts_engine']} | "
            f"Voices: {vdata['available_tts_voices']} | "
            f"local_only={vdata['local_only']} | "
            f"continuous_recording={vdata['continuous_recording']} | "
            f"audio_uploaded={vdata['audio_uploaded']}"
        )
        assert vdata["local_only"] is True
        assert vdata["continuous_recording"] is False
        assert vdata["audio_uploaded"] is False
        assert len(vdata["available_tts_voices"]) >= 1

        # 2. Clear any existing test memories and add a new explicit memory
        client.delete("/api/memories")
        r_add = client.post(
            "/api/memories",
            json={
                "title": "Project Codename & UI Accent",
                "content": "My project codename is Project Bifrost and my preferred UI accent color is Emerald Green.",
                "category": "project",
            },
        )
        assert r_add.status_code == 200, f"Add memory failed: {r_add.text}"
        add_data = r_add.json()
        assert add_data["ok"] is True
        mem_id = add_data["memory"]["memory_id"]
        print(f"[2] Added explicit memory id={mem_id}: '{add_data['memory']['title']}' -> '{add_data['memory']['content']}'")

        # 3. Ensure use_memories_in_chat is enabled and test recall in local Ollama chat
        client.post("/api/settings", json={"use_memories_in_chat": True})
        print("[3] Streaming chat query testing explicit memory injection into local Ollama...")
        memories_used = None
        full_reply = ""
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "What is my project codename and preferred UI accent color? Answer in one short sentence.",
                    }
                ],
                "model": "llama3:latest",
                "provider": "ollama",
                "save_history": False,
            },
        ) as stream:
            assert stream.status_code == 200, f"Stream status={stream.status_code}"
            for line in stream.iter_lines():
                if not line:
                    continue
                pkt = json.loads(line)
                if pkt.get("type") == "meta":
                    memories_used = pkt.get("memories_used")
                elif pkt.get("type") == "token":
                    full_reply += pkt.get("content", "")

        print(f"    -> Stream meta reported memories_used={memories_used}")
        print(f"    -> Assistant reply: {full_reply.strip()}")
        assert memories_used == 1, f"Expected memories_used=1, got {memories_used}"
        assert "bifrost" in full_reply.lower(), f"Expected 'Bifrost' in reply: {full_reply}"

        # 4. Pause (disable) the memory and verify memories_used drops to 0
        r_tog = client.post(f"/api/memories/{mem_id}/toggle", json={"enabled": False})
        assert r_tog.status_code == 200 and r_tog.json()["ok"] is True
        memories_used_paused = None
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "Say OK."}],
                "model": "llama3:latest",
                "provider": "ollama",
                "save_history": False,
            },
        ) as stream:
            for line in stream.iter_lines():
                if not line:
                    continue
                pkt = json.loads(line)
                if pkt.get("type") == "meta":
                    memories_used_paused = pkt.get("memories_used")
        print(f"[4] Paused memory id={mem_id} -> memories_used={memories_used_paused}")
        assert memories_used_paused == 0

        # 5. Delete the memory and verify empty list
        r_del = client.delete(f"/api/memories/{mem_id}")
        assert r_del.status_code == 200 and r_del.json()["ok"] is True
        remaining = r_del.json()["memories"]
        print(f"[5] Deleted memory id={mem_id} -> remaining memories count={len(remaining)}")
        assert len(remaining) == 0

        # 6. Unload model from VRAM
        r_un = client.post("/api/ollama/unload", json={"model": "llama3:latest"})
        assert r_un.status_code == 200
        print(f"[6] Unloaded llama3:latest from VRAM: {r_un.json()['unloaded_models']}")

    print("=== ALL STAGE 5 CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
