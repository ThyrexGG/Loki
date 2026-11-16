"""Milestone 1 End-to-End Verification Script for Loki."""

from __future__ import annotations

import json
import httpx
from _isolated import base_url  # refuses to run outside tests/run_tests.py


def main() -> None:
    with httpx.Client(base_url=base_url(), timeout=60.0) as c:
        # 1. Check CSP and index page
        r_idx = c.get("/")
        assert r_idx.status_code == 200
        csp = r_idx.headers.get("content-security-policy", "")
        print("1. INDEX HTTP:", r_idx.status_code, "| CSP:", csp)

        # 2. Check /api/status
        st = c.get("/api/status").json()
        print("2. OLLAMA CONNECTED:", st["ollama"]["connected"], "| VERSION:", st["ollama"]["version"])
        print("   INSTALLED MODELS:", [m["name"] for m in st["ollama"]["installed_models"]])
        print(
            "   CPU:",
            st["hardware"]["cpu"]["load_percent"],
            "% | RAM:",
            st["hardware"]["ram"]["used_gb"],
            "/",
            st["hardware"]["ram"]["total_gb"],
            "GB",
        )
        print(
            "   GPU:",
            st["hardware"]["gpu"]["name"],
            "| VRAM:",
            st["hardware"]["gpu"]["vram_used_mib"],
            "/",
            st["hardware"]["gpu"]["vram_total_mib"],
            "MiB",
        )

        # 3. Verify Cloud Privacy Gate blocks non-local provider
        r_cloud = c.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}], "provider": "openai"},
        )
        print("3. CLOUD GATE TEST:", r_cloud.text.strip())

        # 4. Verify real local Ollama streaming chat with llama3:latest
        r_chat = c.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "Reply with the exact word: LOKI_LOCAL_OK"}],
                "model": "llama3:latest",
                "num_ctx": 2048,
                "temperature": 0.0,
            },
        )
        events = [json.loads(line) for line in r_chat.text.splitlines() if line.strip()]
        tokens = "".join(e.get("content", "") for e in events if e.get("type") == "token")
        done_evt = next((e for e in events if e.get("type") == "done"), {})
        print("4. CHAT REPLY:", repr(tokens.strip()), "| DONE META:", done_evt)

        # 5. Check VRAM loaded model before unload
        st_loaded = c.get("/api/status").json()
        print("5. RUNNING MODELS IN VRAM BEFORE UNLOAD:", st_loaded["ollama"]["running_models"])

        # 6. Verify Unload Model frees VRAM
        r_un = c.post("/api/ollama/unload", json={"model": "llama3:latest"}).json()
        print(
            "6. UNLOAD RESULT:",
            r_un["unloaded_models"],
            "| RUNNING AFTER UNLOAD:",
            r_un["ollama"]["running_models"],
        )


if __name__ == "__main__":
    main()
