"""Decides which agent handles a request.

Order of precedence:
1. An explicit @mention ("@grok summarize my inbox").
2. Skill keywords in the request ("email", "inbox", ...).
3. An LLM "brain" agent picking from the roster, if one is configured.
4. The default agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .models import Agent

MENTION_RE = re.compile(r"(?:^|\s)@([a-z0-9][a-z0-9-]*)", re.IGNORECASE)


@dataclass
class Route:
    agent: Agent | None
    text: str  # the request with any @mention stripped
    reason: str


def _keyword_score(text: str, agent: Agent) -> int:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    score = 0
    for skill in agent.skills:
        skill = skill.lower().strip()
        if not skill:
            continue
        if " " in skill:
            score += 2 if skill in text.lower() else 0
        elif skill in words or skill + "s" in words:
            score += 1
    return score


def build_router_prompt(text: str, agents: list[Agent]) -> str:
    roster = "\n".join(
        f"- {a.id}: {a.description} (skills: {', '.join(a.skills) or 'general'})" for a in agents
    )
    return (
        "You are the dispatcher for Jarvis, a personal assistant that delegates to agents.\n"
        f"Agents:\n{roster}\n\n"
        f"Request: {text}\n\n"
        "Reply with only the id of the single best agent, or 'none' if no agent fits."
    )


def route(
    text: str,
    agents: list[Agent],
    default_id: str = "",
    brain: Callable[[str], str] | None = None,
) -> Route:
    active = [a for a in agents if a.enabled]
    by_id = {a.id: a for a in active}

    match = MENTION_RE.search(text)
    if match and match.group(1).lower() in by_id:
        agent = by_id[match.group(1).lower()]
        stripped = (text[: match.start()] + " " + text[match.end():]).strip()
        return Route(agent, stripped or text, f"addressed as {agent.handle}")

    scored = sorted(((_keyword_score(text, a), a) for a in active), key=lambda p: -p[0])
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return Route(scored[0][1], text, "matched its skills")

    if brain is not None and active:
        try:
            choice = brain(build_router_prompt(text, active)).strip().strip("`'\".").lower()
        except Exception:
            choice = ""
        if choice in by_id:
            return Route(by_id[choice], text, "picked by the Jarvis brain")

    if default_id in by_id:
        return Route(by_id[default_id], text, "default agent")
    if active:
        return Route(active[0], text, "only available agent" if len(active) == 1 else "first available agent")
    return Route(None, text, "no agents enabled")
