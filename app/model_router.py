"""Per-task local model routing (ADR-010).

Classifies the latest user message as `code`, `reasoning` or `general` with fast, deterministic
heuristics (no extra model call, so no extra GPU load), then picks a specialist model:

    code      -> qwen2.5-coder:7b
    reasoning -> deepseek-r1:8b   (streams its thinking separately)
    general   -> the model the user selected in the picker

A specialist is only used when it is installed and rated `fits` by app/model_fit.py; otherwise the
user's selected model is used. A vague follow-up ("now make it faster") keeps the route of the
recent conversation so a coding thread does not bounce between models.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

ROUTES: dict[str, dict[str, Any]] = {
    "code": {"model": "qwen2.5-coder:7b", "label": "Code"},
    "reasoning": {"model": "deepseek-r1:8b", "label": "Reasoning"},
    # Answers grounded in web results: qwen2.5:7b quoted facts from sources correctly where gemma2:9b
    # repeated an outdated figure from the same pages (measured 2026-11-16, ADR-011).
    "web": {"model": "qwen2.5:7b", "label": "Web"},
    "vision": {"model": "qwen3-vl:8b", "label": "Screen"},
    # Windows troubleshooting: qwen2.5:7b proposed 4 relevant read-only PowerShell checks where gemma2:9b
    # gave one (or a setting change) and the coder model gave none (measured 2026-11-16, ADR-014).
    "pc": {"model": "qwen2.5:7b", "label": "PC help"},  # only model that can see screenshots (ADR-013)
    "general": {"model": None, "label": "General"},
}

_CODE_WORDS = re.compile(
    r"\b(python|javascript|typescript|java|c\+\+|c#|csharp|rust|golang|kotlin|swift|php|ruby|lua|luau|"
    r"sql|html|css|bash|powershell|regex|json|yaml|fastapi|react|node\.?js|django|flask|unity|godot|"
    r"function|method|variable|class|compile[rd]?|syntax|bug|debug|stack ?trace|traceback|exception|"
    r"refactor|unit tests?|script|code|snippet|endpoint|api|repo|git|npm|pip|dockerfile|runtime error|"
    r"website|web ?site|web ?page|landing page|homepage|portfolio site|web app|frontend|front-end|"
    r"html page|browser game|canvas game)\b",
    re.I,
)
_CODE_SHAPES = [
    re.compile(r"```"),
    re.compile(r"^\s*(def|class|import|from|function|const|let|var|public|private|#include|using)\b", re.M),
    re.compile(r"\w+\([^)]*\)\s*[{:]"),
    re.compile(r"=>|::|;\s*$|\{\s*$|</?[a-z][\w-]*>", re.M),
    re.compile(r"\b\w+Error\b|Traceback \(most recent call last\)"),
]
# Strong signals count 2, weak ones 1.
_REASONING_STRONG = re.compile(
    r"\b(step[- ]by[- ]step|prove|proof|derive|solve|calculate|compute|probability|puzzle|riddle|"
    r"equation|integral|derivative|compound interest|reason through|think through)\b",
    re.I,
)
_REASONING_WEAK = re.compile(
    r"\b(how many|how much|odds|logic(al)?|math|work out|estimate|percent(age)?|ratio|"
    r"optimi[sz]e|trade-?offs?)\b",
    re.I,
)
_ARITHMETIC = re.compile(r"\d+(\.\d+)?\s*([-+*/^x×÷]|%\s*of)\s*\d+")


# Asking Loki to build something web-based is a strong coding signal on its own (ADR-015).
_BUILD = re.compile(r"\b(website|web ?site|web ?page|landing page|homepage|portfolio site|web app|browser game|"
                    r"html page|(snake|tetris|pong|breakout|platformer|quiz|memory|clicker) game)\b", re.I)


def _scores(text: str) -> tuple[int, int]:
    code = (len(_CODE_WORDS.findall(text)) + sum(2 for p in _CODE_SHAPES if p.search(text))
            + (2 if _BUILD.search(text) else 0))
    reasoning = (2 * len(_REASONING_STRONG.findall(text)) + len(_REASONING_WEAK.findall(text))
                 + (2 if _ARITHMETIC.search(text) else 0))
    return code, reasoning


_PC_THING = re.compile(
    r"\b(my (pc|computer|laptop|machine|desktop)|windows|win ?1[01]|internet|wi-?fi|network|ethernet|router|dns|"
    r"disk|drive|ssd|hdd|storage|ram|memory usage|cpu|gpu|graphics card|driver|bluetooth|printer|audio|sound|"
    r"speaker|headphones?|microphone|mic|webcam|camera|monitor|display|screen|keyboard|mouse|usb|battery|"
    r"fan|startup|boot|update|blue ?screen|bsod|task manager|explorer|file explorer|defender|antivirus)\b", re.I)
_PC_TROUBLE = re.compile(
    r"\b(slow|slower|lag+y?|laggy|stutter\w*|freez\w*|crash\w*|hang\w*|stuck|not working|doesn'?t work|"
    r"won'?t|can'?t|cannot|fail\w*|error\w*|broken|keeps|disconnect\w*|drops?|dropping|overheat\w*|hot|loud|"
    r"high|100|full|missing|no sound|no internet|black screen|restart\w*|troubleshoot\w*|diagnos\w*|fix)\b", re.I)


def classify_text(text: str) -> tuple[str, str]:
    """Return (task, reason) for one message."""
    if (text or "").lstrip().startswith("I ran this command"):
        # Output sent back from the Run dialog: keep troubleshooting rather than treating it as code.
        return "pc", "you shared the output of a command"
    code, reasoning = _scores(text or "")
    if code >= 2 and code >= reasoning:
        return "code", "looks like a programming question"
    if _PC_THING.search(text or "") and _PC_TROUBLE.search(text or ""):
        return "pc", "looks like a problem with this PC"
    if reasoning >= 2 or (reasoning >= 1 and _ARITHMETIC.search(text or "")):
        return "reasoning", "looks like maths or step-by-step reasoning"
    if code == 1 and reasoning == 0 and len(text) > 40:
        return "code", "mentions programming"
    return "general", "general conversation"


def classify_conversation(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """Classify the latest user message; vague follow-ups inherit the recent specialist route."""
    user_msgs = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    if not user_msgs:
        return "general", "no user message"
    task, reason = classify_text(user_msgs[-1])
    if task == "general" and len(user_msgs[-1]) < 160:
        for prev in reversed(user_msgs[-3:-1]):
            prev_task, _ = classify_text(prev)
            if prev_task != "general":
                return prev_task, f"follow-up in a {ROUTES[prev_task]['label'].lower()} conversation"
    return task, reason


def choose_model(task: str, selected: str, installed: list[dict[str, Any]]) -> tuple[str, bool, str]:
    """Return (model, routed, note). Only routes to an installed specialist rated `fits`."""
    target = ROUTES.get(task, {}).get("model")
    if not target or target == selected:
        return selected, False, ""
    info = next((m for m in installed if m.get("name") == target), None)
    if info is None:
        return selected, False, f"{target} is not installed"
    if info.get("vram_fit") not in ("fits", None):
        return selected, False, f"{target} does not fit in GPU memory"
    return target, True, ""


_capability_cache: dict[str, list[str]] = {}


async def model_capabilities(base_url: str, model: str) -> list[str]:
    """Ollama capabilities for a model (e.g. 'thinking'), cached per process."""
    if model in _capability_cache:
        return _capability_cache[model]
    caps: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{base_url}/api/show", json={"model": model})
            if r.status_code == 200:
                caps = list(r.json().get("capabilities") or [])
    except Exception:
        caps = []
    _capability_cache[model] = caps
    return caps
