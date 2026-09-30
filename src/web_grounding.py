"""
web_grounding.py - Open-source web-search client for grounding
------------------------------------------
Keyless web search through ddgs, called when a local retrieval-distance
heuristic indicates weak context. The caller sends formula fragments to an
external search provider. This is a scoped substitute for web grounding,
not an implementation of Web IQ or an offline search engine.
"""
from __future__ import annotations

from typing import List, Optional

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback name used by older releases
    from duckduckgo_search import DDGS  # type: ignore


def web_ground(query: str, max_results: int = 3) -> List[dict]:
    """Return lightweight, citation-ready grounding snippets.

    Each result: {"title", "snippet", "url"} — analogous to Web IQ's
    structured, citation-ready context contract.
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "title": r.get("title"),
                        "snippet": r.get("body"),
                        "url": r.get("href"),
                    }
                )
    except Exception as exc:  # network unavailable, rate-limited, etc.
        results.append({"title": "web_grounding_error", "snippet": str(exc), "url": None})
    return results


def should_ground(term: str, kb_hits: Optional[list] = None, distance_threshold: float = 0.35) -> bool:
    """Heuristic gate: only call the web if local KB retrieval was weak/empty.
    Mirrors the Foundry-IQ -> Web-IQ routing decision ("freshness needed?").
    """
    if not kb_hits:
        return True
    best = min((h.get("distance") or 1.0) for h in kb_hits)
    return best > distance_threshold
