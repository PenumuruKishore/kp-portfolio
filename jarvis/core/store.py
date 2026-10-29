"""JSON-file persistence for agents, conversation and settings."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Agent, Message, default_agents

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAX_MESSAGES = 1000

DEFAULT_SETTINGS = {
    "owner_name": "Kishore",
    "default_agent": "grok",
    "brain_agent": "",  # agent id used to route ambiguous requests; empty = off
    "context_turns": 6,  # past exchanges with an agent sent along as context
}


class Store:
    def __init__(self, data_dir: str | Path | None = None):
        self.dir = Path(data_dir or os.environ.get("JARVIS_DATA_DIR") or DEFAULT_DATA_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _read(self, name: str, fallback):
        path = self.dir / name
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return fallback

    def _write(self, name: str, data) -> None:
        # Write to a temp file and rename, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.dir / name)

    # Agents
    def agents(self) -> list[Agent]:
        raw = self._read("agents.json", None)
        if raw is None:
            agents = default_agents()
            self.save_agents(agents)
            return agents
        return [Agent.from_dict(a) for a in raw]

    def save_agents(self, agents: list[Agent]) -> None:
        self._write("agents.json", [a.to_dict() for a in agents])

    def upsert_agent(self, agent: Agent) -> None:
        agents = [a for a in self.agents() if a.id != agent.id]
        agents.append(agent)
        self.save_agents(agents)

    def delete_agent(self, agent_id: str) -> None:
        self.save_agents([a for a in self.agents() if a.id != agent_id])

    # Conversation
    def messages(self) -> list[Message]:
        return [Message.from_dict(m) for m in self._read("messages.json", [])]

    def append_messages(self, *new: Message) -> None:
        messages = self.messages() + list(new)
        self._write("messages.json", [m.to_dict() for m in messages[-MAX_MESSAGES:]])

    def clear_messages(self) -> None:
        self._write("messages.json", [])

    # Settings
    def settings(self) -> dict:
        return {**DEFAULT_SETTINGS, **self._read("settings.json", {})}

    def save_settings(self, settings: dict) -> None:
        self._write("settings.json", settings)
