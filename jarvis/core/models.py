"""Data models for Jarvis: agents and the messages exchanged with them."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field

# Connector kinds Jarvis knows how to talk to.
KIND_GROK = "grok"
KIND_CLAUDE = "claude"
KIND_OPENAI = "openai_compatible"
KIND_WEBHOOK = "webhook"

KIND_LABELS = {
    KIND_GROK: "Grok (xAI API)",
    KIND_CLAUDE: "Claude (Anthropic API)",
    KIND_OPENAI: "OpenAI-compatible API",
    KIND_WEBHOOK: "Custom webhook (your own bot server)",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "agent"


@dataclass
class Agent:
    name: str
    kind: str
    description: str = ""
    # Keywords that make Jarvis route a request to this agent, e.g. "email", "inbox".
    skills: list[str] = field(default_factory=list)
    # One-click commands shown on the Command Center.
    quick_actions: list[str] = field(default_factory=list)
    endpoint: str = ""
    model: str = ""
    # Name of the env var / Streamlit secret holding the API key or bearer token.
    # The key itself is never written to disk.
    api_key_env: str = ""
    system_prompt: str = ""
    icon: str = "🤖"
    enabled: bool = True
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = slugify(self.name)

    @property
    def handle(self) -> str:
        """The @mention used to address this agent directly in chat."""
        return "@" + self.id

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Message:
    role: str  # "user" | "agent" | "system"
    content: str
    agent_id: str = ""
    route_reason: str = ""
    latency_ms: int = 0
    error: bool = False
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


GROK_MAIL_PROMPT = (
    "You are Kishore's email agent, working on behalf of Jarvis, his personal "
    "assistant. You manage his Gmail: triage the inbox, summarize threads, draft "
    "replies, and flag anything urgent. Be concise and use bullet points. Never "
    "send an email without explicit confirmation."
)


def default_agents() -> list[Agent]:
    """Agents Jarvis starts with on first launch."""
    return [
        Agent(
            id="grok",
            name="Grok Mail",
            kind=KIND_GROK,
            icon="📧",
            description="Manages Gmail: triage, summaries, drafts and follow-ups.",
            skills=["email", "gmail", "inbox", "mail", "unread", "reply", "draft",
                    "newsletter", "unsubscribe", "thread", "sender"],
            quick_actions=[
                "Summarize my unread emails",
                "What needs a reply from me today?",
                "Draft replies to anything urgent",
            ],
            endpoint="https://api.x.ai/v1",
            model="grok-4",
            api_key_env="XAI_API_KEY",
            system_prompt=GROK_MAIL_PROMPT,
        ),
    ]
