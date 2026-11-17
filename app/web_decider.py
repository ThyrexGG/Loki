"""Decide automatically whether a chat message needs the web (ADR-011).

Deterministic heuristics (no extra model call):
- A pasted link            -> read that page.
- Explicit request         -> "search ...", "look up ...", "google ...", "find online ...".
- Time-sensitive facts     -> latest / news / today / current / price / weather / score / release ...
- Who/when/where questions about specific named things -> search.
- Code, maths, creative writing, small talk -> stay offline (unless explicitly asked).
"""

from __future__ import annotations

import re
from typing import Any

from app.model_router import classify_text
from app.web_tools import find_urls

_EXPLICIT = re.compile(
    r"^\s*(please\s+)?(can you\s+|could you\s+)?(search( the web| online| for)?|look up|google|"
    r"find (me )?(online|on the web)|browse|check online)\b|\b(search the web|on the internet|online sources?)\b",
    re.I,
)
_TIME_SENSITIVE = re.compile(
    r"\b(latest|newest|news|today|tonight|yesterday|this (week|month|year)|right now|currently|"
    r"current(ly)?|recent(ly)?|up[- ]to[- ]date|20(2[4-9]|3\d)|price|prices|cost of|how much (is|does|are)|"
    r"weather|forecast|score|scores|who won|results? of|release date|released|launch(ed)?|"
    r"exchange rate|stock|patch notes|update[sd]?|version of|schedule|tickets?|open now|near me)\b",
    re.I,
)
_ENTITY_QUESTION = re.compile(r"^\s*(who|when|where)\b|^\s*what (happened|is happening)\b", re.I)
_PROPER_NOUN = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*")
_CREATIVE_OR_CHAT = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|good (morning|night|evening))\b|"
    r"\b(write|compose|draft) (me )?(a |an )?(poem|story|song|haiku|joke|essay|email|letter|caption)\b",
    re.I,
)
_FILLER = re.compile(
    r"^\s*(please\s+)?(can you|could you|would you)?\s*(please\s+)?"
    r"(search( the web| online)?( for)?|look up|google|find (me )?(online|on the web)?|tell me|browse( for)?)\s*",
    re.I,
)


def build_query(messages: list[dict[str, Any]]) -> str:
    users = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    last = users[-1] if users else ""
    q = _FILLER.sub("", last).strip().rstrip("?.! ")
    # Short follow-ups ("and its price?") need the previous question for context.
    if len(q.split()) <= 5 and len(users) >= 2:
        q = f"{_FILLER.sub('', users[-2]).strip().rstrip('?.! ')} {q}"
    return " ".join(q.split())[:200]


def decide(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {"mode": "read"|"search"|None, "query": str, "urls": [...], "reason": str}."""
    users = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    last = users[-1] if users else ""
    none = {"mode": None, "query": "", "urls": [], "reason": ""}
    if not last.strip():
        return none

    urls = find_urls(last)
    if urls:
        return {"mode": "read", "query": "", "urls": urls, "reason": "you shared a link"}

    if _EXPLICIT.search(last):
        return {"mode": "search", "query": build_query(messages), "urls": [], "reason": "you asked to search"}

    task, _ = classify_text(last)
    has_code_block = "```" in last or "\n" in last.strip()
    if _CREATIVE_OR_CHAT.search(last) or len(last.split()) < 3:
        return none
    if task in ("code", "reasoning"):
        # Allow web search for short single-line version/release/latest questions about programming tools
        if not (task == "code" and not has_code_block and len(last) < 160 and _TIME_SENSITIVE.search(last)):
            return none

    if _TIME_SENSITIVE.search(last):
        return {"mode": "search", "query": build_query(messages), "urls": [],
                "reason": "the answer may have changed recently"}
    if _ENTITY_QUESTION.search(last) and _PROPER_NOUN.search(last):
        return {"mode": "search", "query": build_query(messages), "urls": [],
                "reason": "it asks about a specific person, place or thing"}
    return none
