"""Model Gateway, Three-Switch Cloud Privacy Gate, and Outbound Activity/Cost Visibility Ledger."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx

from app.config import (
    ACTIVITY_LEDGER_FILE,
    DEFAULT_SETTINGS,
    ensure_data_dir,
    load_settings,
    save_settings,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# Approximate public API pricing per 1,000,000 tokens (USD) for cost visibility.
# Note: Consumer chat subscriptions (ChatGPT Plus, Claude Pro, Gemini Advanced) do NOT include API billing.
PRICING_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "openai": {"input": 0.15, "output": 0.60},      # gpt-4o-mini class
    "anthropic": {"input": 0.80, "output": 4.00},   # claude-3-5-haiku class
    "gemini": {"input": 0.15, "output": 0.60},      # gemini-2.5-flash class
}


class ActivityLedger:
    """
    Persists an inspectable log of all Model Gateway calls in `data/activity_ledger.json`.
    Clearly distinguishes 100% local Ollama calls (`data_left_pc=False`, `$0.00`) from
    blocked cloud attempts (`data_left_pc=False`) and explicitly opted-in cloud calls.
    """

    def list_entries(self) -> list[dict[str, Any]]:
        ensure_data_dir()
        if not ACTIVITY_LEDGER_FILE.exists():
            return []
        try:
            data = json.loads(ACTIVITY_LEDGER_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_entries(self, entries: list[dict[str, Any]]) -> None:
        ensure_data_dir()
        capped = entries[:100]
        ACTIVITY_LEDGER_FILE.write_text(json.dumps(capped, indent=2), encoding="utf-8")

    def record_entry(
        self,
        *,
        kind: str,
        provider: str,
        model: str,
        status: str,
        data_left_pc: bool,
        bytes_sent_external: int = 0,
        prompt_tokens: int = 0,
        eval_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        detail: str = "",
    ) -> dict[str, Any]:
        entry = {
            "entry_id": f"act-{int(time.time())}-{uuid.uuid4().hex[:6]}",
            "timestamp": _now_iso(),
            "kind": kind,
            "provider": provider,
            "model": model,
            "status": status,
            "data_left_pc": bool(data_left_pc),
            "bytes_sent_external": int(bytes_sent_external),
            "prompt_tokens": int(prompt_tokens),
            "eval_tokens": int(eval_tokens),
            "estimated_cost_usd": round(float(estimated_cost_usd), 6),
            "detail": detail,
        }
        entries = self.list_entries()
        entries.insert(0, entry)
        self._save_entries(entries)
        return entry

    def get_summary(self) -> dict[str, Any]:
        entries = self.list_entries()
        local_calls = sum(1 for e in entries if e.get("provider") == "ollama" and e.get("status") == "completed")
        is_web = lambda e: str(e.get("kind", "")).startswith("web")  # noqa: E731
        cloud_calls = sum(
            1 for e in entries if e.get("provider") != "ollama" and e.get("data_left_pc") is True and not is_web(e)
        )
        web_requests = sum(1 for e in entries if is_web(e))
        blocked_attempts = sum(
            1 for e in entries if e.get("status") in ("blocked_by_privacy_gate", "missing_env_api_key")
        )
        total_bytes_ext = sum(int(e.get("bytes_sent_external", 0)) for e in entries)
        total_cost = round(sum(float(e.get("estimated_cost_usd", 0.0)) for e in entries), 6)
        return {
            "total_entries": len(entries),
            "local_calls_count": local_calls,
            "cloud_calls_count": cloud_calls,
            "web_requests_count": web_requests,
            "blocked_cloud_attempts": blocked_attempts,
            "total_bytes_sent_external": total_bytes_ext,
            "total_estimated_cost_usd": total_cost,
            "entries": entries,
        }

    def clear_ledger(self) -> dict[str, Any]:
        if ACTIVITY_LEDGER_FILE.exists():
            ACTIVITY_LEDGER_FILE.unlink(missing_ok=True)
        return {"ok": True, "summary": self.get_summary()}


class CloudProviderGateway:
    """
    Manages the Three-Switch Cloud Privacy Gate and optional cloud provider adapters
    (OpenAI, Anthropic, Google Gemini).
    - Local-only is the default (`cloud_global_opt_in = False`).
    - API keys are NEVER stored in files or logs; they are checked exclusively from
      process environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`).
    """

    PROVIDER_SPECS: dict[str, dict[str, str]] = {
        "openai": {
            "display_name": "ChatGPT (OpenAI API)",
            "default_model": "gpt-4o-mini",
            "env_var": "OPENAI_API_KEY",
            "endpoint": "https://api.openai.com/v1/chat/completions",
        },
        "anthropic": {
            "display_name": "Claude (Anthropic API)",
            "default_model": "claude-3-5-haiku-latest",
            "env_var": "ANTHROPIC_API_KEY",
            "endpoint": "https://api.anthropic.com/v1/messages",
        },
        "gemini": {
            "display_name": "Gemini (Google API)",
            "default_model": "gemini-2.5-flash",
            "env_var": "GEMINI_API_KEY",
            "endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        },
    }

    def get_providers_status(self) -> dict[str, Any]:
        settings = load_settings()
        global_opt = bool(settings.get("cloud_global_opt_in", False))
        saved_provs = settings.get("cloud_providers", {})

        providers_out: dict[str, Any] = {}
        for key, spec in self.PROVIDER_SPECS.items():
            p_cfg = saved_provs.get(key, {})
            env_name = spec["env_var"]
            has_key = bool(os.environ.get(env_name, "").strip())
            providers_out[key] = {
                "id": key,
                "display_name": spec["display_name"],
                "default_model": p_cfg.get("default_model") or spec["default_model"],
                "enabled": bool(p_cfg.get("enabled", False)),
                "env_var": env_name,
                "api_key_in_env": has_key,
                "endpoint": spec["endpoint"],
                "billing_note": "Separate API billing required; consumer chat subscriptions do not include API access.",
            }

        return {
            "cloud_global_opt_in": global_opt,
            "local_default": not global_opt,
            "providers": providers_out,
        }

    def update_gate_settings(
        self,
        *,
        cloud_global_opt_in: bool | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
        default_model: str | None = None,
    ) -> dict[str, Any]:
        settings = load_settings()
        if cloud_global_opt_in is not None:
            settings["cloud_global_opt_in"] = bool(cloud_global_opt_in)
            # If global opt-in is turned off, also force all individual providers off for safety
            if not settings["cloud_global_opt_in"]:
                provs = settings.get("cloud_providers", dict(DEFAULT_SETTINGS["cloud_providers"]))
                for k in provs:
                    provs[k]["enabled"] = False
                settings["cloud_providers"] = provs

        if provider and provider in self.PROVIDER_SPECS:
            provs = settings.get("cloud_providers", dict(DEFAULT_SETTINGS["cloud_providers"]))
            if provider not in provs:
                provs[provider] = dict(DEFAULT_SETTINGS["cloud_providers"][provider])
            if enabled is not None:
                provs[provider]["enabled"] = bool(enabled)
            if default_model:
                provs[provider]["default_model"] = str(default_model).strip()
            settings["cloud_providers"] = provs

        save_settings(settings)
        return self.get_providers_status()

    def check_three_switch_gate(
        self, provider: str, cloud_request_opt_in: bool
    ) -> tuple[bool, str, dict[str, bool]]:
        """
        Verify all three switches of the Cloud Privacy Gate:
        1. Switch 1: Global Cloud Opt-In (`cloud_global_opt_in`)
        2. Switch 2: Per-Provider Opt-In (`cloud_providers[provider].enabled`)
        3. Switch 3: Per-Request Opt-In (`cloud_request_opt_in`)
        """
        settings = load_settings()
        sw_global = bool(settings.get("cloud_global_opt_in", False))
        prov_cfg = settings.get("cloud_providers", {}).get(provider, {})
        sw_provider = bool(prov_cfg.get("enabled", False))
        sw_request = bool(cloud_request_opt_in)

        switches = {
            "global_opt_in": sw_global,
            "provider_enabled": sw_provider,
            "request_opt_in": sw_request,
        }

        if provider not in self.PROVIDER_SPECS:
            return (False, f"Unknown cloud provider '{provider}'.", switches)

        missing = []
        if not sw_global:
            missing.append("Switch 1 (Global Cloud Opt-In is OFF)")
        if not sw_provider:
            missing.append(f"Switch 2 (Provider '{provider}' is DISABLED)")
        if not sw_request:
            missing.append("Switch 3 (Per-Request Cloud Opt-In was not checked)")

        if missing:
            reason = (
                f"Blocked by Loki Three-Switch Privacy Gate for '{provider}': "
                + "; ".join(missing)
                + ". Zero bytes left your PC."
            )
            return (False, reason, switches)

        return (True, "All three cloud opt-in switches verified.", switches)

    @staticmethod
    def estimate_cost(provider: str, prompt_tokens: int, eval_tokens: int) -> float:
        rates = PRICING_PER_1M_TOKENS.get(provider, {"input": 0.50, "output": 1.50})
        cost = (prompt_tokens / 1_000_000.0) * rates["input"] + (
            eval_tokens / 1_000_000.0
        ) * rates["output"]
        return round(cost, 6)

    async def stream_cloud_chat(
        self,
        *,
        provider: str,
        model: str | None,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
        cloud_request_opt_in: bool,
        memories_used: int = 0,
    ) -> AsyncGenerator[str, None]:
        """
        Execute an opt-in cloud request ONLY if all three switches of the Privacy Gate pass
        and the corresponding API key environment variable is present.
        """
        spec = self.PROVIDER_SPECS.get(provider, {})
        resolved_model = model or spec.get("default_model", "cloud-model")
        if resolved_model == "llama3:latest" and spec.get("default_model"):
            resolved_model = spec["default_model"]

        allowed, reason, _ = self.check_three_switch_gate(provider, cloud_request_opt_in)
        if not allowed:
            activity_ledger.record_entry(
                kind="chat",
                provider=provider,
                model=resolved_model,
                status="blocked_by_privacy_gate",
                data_left_pc=False,
                bytes_sent_external=0,
                detail=reason,
            )
            yield json.dumps({"type": "error", "error": reason}) + "\n"
            return

        env_var = spec.get("env_var", "")
        api_key = os.environ.get(env_var, "").strip()
        if not api_key:
            msg = (
                f"Cloud provider '{provider}' passed the Three-Switch Opt-In Gate, but environment variable "
                f"'{env_var}' is not set. Loki never stores API keys in source code or settings files. "
                "Zero bytes left your PC."
            )
            activity_ledger.record_entry(
                kind="chat",
                provider=provider,
                model=resolved_model,
                status="missing_env_api_key",
                data_left_pc=False,
                bytes_sent_external=0,
                detail=msg,
            )
            yield json.dumps({"type": "error", "error": msg}) + "\n"
            return

        # All 3 switches + env API key verified
        yield json.dumps(
            {
                "type": "meta",
                "provider": f"{provider} (cloud opt-in)",
                "endpoint": spec.get("endpoint", ""),
                "model": resolved_model,
                "num_ctx": 0,
                "temperature": temperature,
                "memories_used": memories_used,
                "data_left_pc": True,
            }
        ) + "\n"

        t_start = time.perf_counter()
        try:
            reply_text, p_tok, c_tok, bytes_sent = await self._call_cloud_provider(
                provider=provider,
                api_key=api_key,
                model=resolved_model,
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
            )
            elapsed = round(time.perf_counter() - t_start, 2)
            cost_usd = self.estimate_cost(provider, p_tok, c_tok)

            yield json.dumps({"type": "token", "content": reply_text}) + "\n"
            activity_ledger.record_entry(
                kind="chat",
                provider=provider,
                model=resolved_model,
                status="completed",
                data_left_pc=True,
                bytes_sent_external=bytes_sent,
                prompt_tokens=p_tok,
                eval_tokens=c_tok,
                estimated_cost_usd=cost_usd,
                detail=f"Explicitly opted-in cloud request to {provider}/{resolved_model}",
            )
            yield json.dumps(
                {
                    "type": "done",
                    "model": resolved_model,
                    "provider": f"{provider} (cloud opt-in)",
                    "total_duration_s": elapsed,
                    "prompt_tokens": p_tok,
                    "eval_tokens": c_tok,
                    "tokens_per_sec": round(c_tok / elapsed, 1) if elapsed > 0 else None,
                    "estimated_cost_usd": cost_usd,
                    "data_left_pc": True,
                }
            ) + "\n"
        except Exception as exc:
            err_msg = f"Cloud provider '{provider}' error: {exc}"
            activity_ledger.record_entry(
                kind="chat",
                provider=provider,
                model=resolved_model,
                status="error",
                data_left_pc=True,
                detail=err_msg,
            )
            yield json.dumps({"type": "error", "error": err_msg}) + "\n"

    async def _call_cloud_provider(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> tuple[str, int, int, int]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "openai":
                oa_msgs = [{"role": "system", "content": system_prompt}] + [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                    if m.get("role") in ("user", "assistant")
                ]
                body = {"model": model, "messages": oa_msgs, "temperature": temperature}
                raw_bytes = len(json.dumps(body).encode("utf-8"))
                resp = await client.post(
                    self.PROVIDER_SPECS["openai"]["endpoint"],
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return (
                    text,
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                    raw_bytes,
                )

            if provider == "anthropic":
                an_msgs = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                    if m.get("role") in ("user", "assistant")
                ]
                body = {
                    "model": model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": an_msgs,
                    "temperature": temperature,
                }
                raw_bytes = len(json.dumps(body).encode("utf-8"))
                resp = await client.post(
                    self.PROVIDER_SPECS["anthropic"]["endpoint"],
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                blocks = data.get("content", [])
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                usage = data.get("usage", {})
                return (
                    text,
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    raw_bytes,
                )

            if provider == "gemini":
                contents = []
                for m in messages:
                    if m.get("role") in ("user", "assistant"):
                        role = "user" if m["role"] == "user" else "model"
                        contents.append({"role": role, "parts": [{"text": m["content"]}]})
                body = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": {"temperature": temperature},
                }
                raw_bytes = len(json.dumps(body).encode("utf-8"))
                url = f"{self.PROVIDER_SPECS['gemini']['endpoint']}/{model}:generateContent"
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts)
                usage = data.get("usageMetadata", {})
                return (
                    text,
                    int(usage.get("promptTokenCount", 0)),
                    int(usage.get("candidatesTokenCount", 0)),
                    raw_bytes,
                )

            raise ValueError(f"Unsupported cloud provider: {provider}")


activity_ledger = ActivityLedger()
cloud_gateway = CloudProviderGateway()
