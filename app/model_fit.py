"""VRAM fit ratings for local Ollama models (8 GB RTX 5050 budget).

A model "fits" when its weights plus the KV cache / CUDA runtime overhead fit in total VRAM.
Models that do not fit still run, but Ollama offloads layers to the CPU, which is much slower.
Sizes are GiB on both sides (`size_gb` from Ollama, `vram_total_mib / 1024` from nvidia-smi).
"""

from __future__ import annotations

from typing import Any

PREFERRED_DEFAULT = "gemma2:9b"
TIGHT_MARGIN_GB = 0.5  # weights fit, but with context they will likely spill a few layers to CPU

FIT_LABELS = {
    "fits": "Fits in GPU memory",
    "tight": "Tight fit: may run partly on CPU",
    "offload": "Too big for GPU memory: runs partly on CPU (slower)",
    "unknown": "GPU memory unknown",
}


def overhead_gb(num_ctx: int = 4096) -> float:
    """Approximate KV cache + runtime overhead: ~1 GiB runtime plus ~1 GiB of KV cache per 4k tokens
    (1.5 GiB at 2k, 2 GiB at 4k, 3 GiB at 8k). Measured: gemma2:9b at 4k context loads ~6.6 GiB total."""
    return 1.0 + 1.0 * (max(512, int(num_ctx or 4096)) / 4096)


def vram_total_gb(gpu: dict[str, Any] | None) -> float | None:
    if not gpu or not gpu.get("available") or not gpu.get("vram_total_mib"):
        return None
    return gpu["vram_total_mib"] / 1024


def classify(size_gb: float | None, vram_gb: float | None, num_ctx: int = 4096) -> str:
    if not vram_gb or not size_gb:
        return "unknown"
    if size_gb + overhead_gb(num_ctx) <= vram_gb:
        return "fits"
    if size_gb <= vram_gb - TIGHT_MARGIN_GB:
        return "tight"
    return "offload"


def annotate_models(models: list[dict[str, Any]], gpu: dict[str, Any] | None, num_ctx: int = 4096) -> list[dict[str, Any]]:
    """Add `vram_fit` and `vram_fit_label` to each installed model entry (in place, also returned)."""
    vram = vram_total_gb(gpu)
    for m in models:
        fit = classify(m.get("size_gb"), vram, num_ctx)
        m["vram_fit"] = fit
        m["vram_fit_label"] = FIT_LABELS[fit]
    return models


def pick_default_model(models: list[dict[str, Any]], gpu: dict[str, Any] | None, num_ctx: int = 4096) -> str | None:
    """Choose a model when the saved one is missing: the preferred default if it fits, else the
    largest model that fits, else the smallest installed model. Never blindly the first in the list."""
    if not models:
        return None
    vram = vram_total_gb(gpu)
    names = {m["name"] for m in models}
    if vram is None:
        return PREFERRED_DEFAULT if PREFERRED_DEFAULT in names else min(models, key=lambda m: m.get("size_gb") or 0)["name"]
    fitting = [m for m in models if classify(m.get("size_gb"), vram, num_ctx) == "fits"]
    if PREFERRED_DEFAULT in {m["name"] for m in fitting}:
        return PREFERRED_DEFAULT
    if fitting:
        return max(fitting, key=lambda m: m.get("size_gb") or 0)["name"]
    return min(models, key=lambda m: m.get("size_gb") or 0)["name"]
