"""The orchestrator: takes a request, routes it, calls the agent, records the result."""

from __future__ import annotations

import time

from . import connectors
from .models import Message
from .router import route
from .store import Store


def agent_history(messages: list[Message], agent_id: str, turns: int) -> list[dict]:
    """The last `turns` successful exchanges with one agent, in chat format."""
    pairs: list[tuple[str, str]] = []
    pending = None  # the latest request to this agent still awaiting its reply
    for m in messages:
        if m.agent_id != agent_id:
            continue
        if m.role == "user":
            pending = m.content
        elif m.role == "agent" and pending is not None:
            if not m.error:
                pairs.append((pending, m.content))
            pending = None
    history: list[dict] = []
    for request, reply in pairs[-turns:] if turns > 0 else []:
        history += [{"role": "user", "content": request}, {"role": "assistant", "content": reply}]
    return history


def _brain_for(store: Store, agents):
    brain_id = store.settings().get("brain_agent")
    brain = next((a for a in agents if a.id == brain_id and a.enabled), None)
    if brain is None:
        return None
    return lambda prompt: connectors.send(brain, [{"role": "user", "content": prompt}])


def handle(store: Store, text: str, agent_id: str = "") -> tuple[Message, Message]:
    """Dispatch one request. Pass agent_id to skip routing and use that agent."""
    settings = store.settings()
    agents = store.agents()

    if agent_id:
        agent = next((a for a in agents if a.id == agent_id and a.enabled), None)
        r_text, reason = text, "chosen manually"
    else:
        r = route(text, agents, settings.get("default_agent", ""), _brain_for(store, agents))
        agent, r_text, reason = r.agent, r.text, r.reason

    if agent is None:
        user = Message("user", text)
        reply = Message("system", "No agent is available. Add or enable one on the Agents page.", error=True)
        store.append_messages(user, reply)
        return user, reply

    history = agent_history(store.messages(), agent.id, int(settings.get("context_turns", 6)))
    history.append({"role": "user", "content": r_text})

    user = Message("user", text, agent_id=agent.id, route_reason=reason)
    start = time.monotonic()
    try:
        content, error = connectors.send(agent, history), False
    except connectors.AgentError as exc:
        content, error = str(exc), True
    reply = Message(
        "agent", content, agent_id=agent.id, route_reason=reason,
        latency_ms=int((time.monotonic() - start) * 1000), error=error,
    )
    store.append_messages(user, reply)
    return user, reply
