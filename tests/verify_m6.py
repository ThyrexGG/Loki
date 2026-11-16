"""Stage 6 / Task 6.1 Verification Script for Loki:
Three-Switch Cloud Provider Gateway & Outbound Activity/Cost Visibility Ledger.
"""

import json
import sys
import httpx
from _isolated import base_url  # refuses to run outside tests/run_tests.py

BASE_URL = base_url()


def _read_stream_packets(client: httpx.Client, payload: dict) -> list[dict]:
    packets = []
    with client.stream("POST", "/api/chat/stream", json=payload) as stream:
        assert stream.status_code == 200, f"HTTP {stream.status_code}"
        for line in stream.iter_lines():
            if line:
                packets.append(json.loads(line))
    return packets


def main() -> int:
    print("=== Loki Stage 6 Verification (Cloud Gateway & Activity/Cost Ledger) ===")
    with httpx.Client(base_url=BASE_URL, timeout=90.0) as client:
        # 1. Reset gate to strict local-only default & clear ledger
        client.post("/api/cloud/settings", json={"cloud_global_opt_in": False})
        client.delete("/api/activity/ledger")

        r_st = client.get("/api/cloud/status")
        assert r_st.status_code == 200
        cg = r_st.json()
        print(
            f"[1] Default Cloud Gate: cloud_global_opt_in={cg['cloud_global_opt_in']} | "
            f"local_default={cg['local_default']} | "
            f"openai.enabled={cg['providers']['openai']['enabled']} | "
            f"anthropic.enabled={cg['providers']['anthropic']['enabled']} | "
            f"gemini.enabled={cg['providers']['gemini']['enabled']}"
        )
        assert cg["cloud_global_opt_in"] is False
        assert cg["local_default"] is True
        for p in ("openai", "anthropic", "gemini"):
            assert cg["providers"][p]["enabled"] is False

        # 2. Test Block #1: All switches off -> attempt OpenAI call
        pkts_1 = _read_stream_packets(
            client,
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "provider": "openai",
                "cloud_request_opt_in": False,
            },
        )
        assert pkts_1[0]["type"] == "error"
        assert "Switch 1" in pkts_1[0]["error"] and "Switch 2" in pkts_1[0]["error"]
        print(f"[2] Block #1 (All Switches Off -> OpenAI): {pkts_1[0]['error']}")

        # 3. Test Block #2: Enable Switch 1 (Global), leave Switch 2 (Anthropic) disabled
        client.post("/api/cloud/settings", json={"cloud_global_opt_in": True})
        pkts_2 = _read_stream_packets(
            client,
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "provider": "anthropic",
                "cloud_request_opt_in": True,
            },
        )
        assert pkts_2[0]["type"] == "error"
        assert "Switch 2 (Provider 'anthropic' is DISABLED)" in pkts_2[0]["error"]
        print(f"[3] Block #2 (Switch 2 Disabled -> Anthropic): {pkts_2[0]['error']}")

        # 4. Test Block #3: Enable Switch 1 + Switch 2 (Gemini), omit Switch 3 (Per-Request Opt-In)
        client.post("/api/cloud/settings", json={"provider": "gemini", "enabled": True})
        pkts_3 = _read_stream_packets(
            client,
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "provider": "gemini",
                "cloud_request_opt_in": False,
            },
        )
        assert pkts_3[0]["type"] == "error"
        assert "Switch 3 (Per-Request Cloud Opt-In was not checked)" in pkts_3[0]["error"]
        print(f"[4] Block #3 (Switch 3 False -> Gemini): {pkts_3[0]['error']}")

        # 5. Test Block #4: Enable all 3 switches for OpenAI -> verify env-var API key gate
        client.post("/api/cloud/settings", json={"provider": "openai", "enabled": True})
        pkts_4 = _read_stream_packets(
            client,
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "provider": "openai",
                "cloud_request_opt_in": True,
            },
        )
        assert pkts_4[0]["type"] == "error"
        assert "OPENAI_API_KEY" in pkts_4[0]["error"]
        print(f"[5] Block #4 (Env Key Gate -> OpenAI): {pkts_4[0]['error']}")

        # 6. Lock Global Cloud Opt-In back to OFF and verify all providers auto-disable
        r_lock = client.post("/api/cloud/settings", json={"cloud_global_opt_in": False})
        locked_cg = r_lock.json()["cloud_gateway"]
        assert locked_cg["cloud_global_opt_in"] is False
        for p in ("openai", "anthropic", "gemini"):
            assert locked_cg["providers"][p]["enabled"] is False
        print("[6] Re-locked Global Cloud Opt-In -> all cloud providers auto-disabled.")

        # 7. Run a 100% local Ollama chat and verify the Activity & Cost Ledger
        pkts_local = _read_stream_packets(
            client,
            {
                "messages": [{"role": "user", "content": "Reply with the single word LOCAL."}],
                "provider": "ollama",
                "model": "llama3:latest",
                "save_history": False,
            },
        )
        reply = "".join(p.get("content", "") for p in pkts_local if p.get("type") == "token").strip()
        print(f"[7] Local Ollama chat completed: '{reply}'")

        r_led = client.get("/api/activity/ledger")
        assert r_led.status_code == 200
        ledger = r_led.json()
        print(
            f"[8] Activity Ledger Summary: total_entries={ledger['total_entries']} | "
            f"local_calls={ledger['local_calls_count']} | "
            f"blocked_cloud={ledger['blocked_cloud_attempts']} | "
            f"cloud_calls={ledger['cloud_calls_count']} | "
            f"bytes_sent_external={ledger['total_bytes_sent_external']} | "
            f"est_cost=${ledger['total_estimated_cost_usd']:.6f}"
        )
        assert ledger["local_calls_count"] == 1
        assert ledger["blocked_cloud_attempts"] == 4
        assert ledger["cloud_calls_count"] == 0
        assert ledger["total_bytes_sent_external"] == 0
        assert ledger["total_estimated_cost_usd"] == 0.0
        for entry in ledger["entries"]:
            assert entry["data_left_pc"] is False

        # 8. Unload model from VRAM
        r_un = client.post("/api/ollama/unload", json={"model": "llama3:latest"})
        assert r_un.status_code == 200
        print(f"[9] Unloaded llama3:latest from VRAM: {r_un.json()['unloaded_models']}")

    print("=== ALL STAGE 6 CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
