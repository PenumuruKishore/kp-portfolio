"""Connectors: how Jarvis sends a conversation to each kind of agent.

Every connector takes an Agent plus a chat history in the common
[{"role": "user"|"assistant", "content": str}, ...] shape and returns the
agent's reply as text, raising AgentError on any failure.
"""

from __future__ import annotations

import os

import requests

from .models import KIND_CLAUDE, KIND_GROK, KIND_OPENAI, KIND_WEBHOOK, Agent

TIMEOUT_S = 120
XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
# Models that accept server-side refusal fallbacks.
CLAUDE_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AgentError(Exception):
    """Raised when an agent can't be reached or returns an unusable reply."""


def resolve_secret(name: str) -> str:
    """Look a secret up in the environment, then in Streamlit secrets."""
    if not name:
        return ""
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def is_configured(agent: Agent) -> tuple[bool, str]:
    """Whether the agent has everything it needs, and if not, what's missing."""
    if agent.kind in (KIND_OPENAI, KIND_WEBHOOK) and not agent.endpoint:
        return False, "No endpoint URL set"
    if agent.kind in (KIND_GROK, KIND_CLAUDE, KIND_OPENAI) and not resolve_secret(agent.api_key_env):
        return False, f"Secret `{agent.api_key_env or '(unset)'}` not found"
    return True, "Ready"


def _with_system(agent: Agent, history: list[dict]) -> list[dict]:
    messages = list(history)
    if agent.system_prompt:
        messages.insert(0, {"role": "system", "content": agent.system_prompt})
    return messages


def _post(url: str, headers: dict, payload: dict) -> requests.Response:
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise AgentError(f"Could not reach {url}: {exc}") from exc
    if resp.status_code >= 400:
        raise AgentError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
    return resp


def _chat_completions(agent: Agent, history: list[dict], base_url: str) -> str:
    """OpenAI-style /chat/completions, used by xAI (Grok) and compatible servers."""
    key = resolve_secret(agent.api_key_env)
    if not key:
        raise AgentError(f"Missing API key: set `{agent.api_key_env}` in env or Streamlit secrets.")
    resp = _post(
        base_url.rstrip("/") + "/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": agent.model, "messages": _with_system(agent, history)},
    )
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AgentError(f"Unexpected response shape: {resp.text[:300]}") from exc


def _grok(agent: Agent, history: list[dict]) -> str:
    return _chat_completions(agent, history, agent.endpoint or XAI_BASE_URL)


def _openai_compatible(agent: Agent, history: list[dict]) -> str:
    return _chat_completions(agent, history, agent.endpoint)


def _claude(agent: Agent, history: list[dict]) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise AgentError("Install the `anthropic` package to use Claude agents.") from exc

    key = resolve_secret(agent.api_key_env or "ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=key or None, timeout=TIMEOUT_S)
    model = agent.model or DEFAULT_CLAUDE_MODEL
    params = dict(model=model, max_tokens=16000, messages=history)
    if agent.system_prompt:
        params["system"] = agent.system_prompt
    try:
        if model in CLAUDE_FALLBACK_MODELS:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError as exc:
        raise AgentError("Claude rejected the API key.") from exc
    except anthropic.RateLimitError as exc:
        raise AgentError("Claude rate limit hit; try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise AgentError(f"Claude API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AgentError(f"Could not reach the Claude API: {exc}") from exc

    if response.stop_reason == "refusal":
        raise AgentError("Claude declined this request.")
    text = "".join(b.text for b in response.content if b.type == "text")
    if not text:
        raise AgentError("Claude returned an empty reply.")
    return text


def _webhook(agent: Agent, history: list[dict]) -> str:
    """POST to your own bot server.

    Request:  {"agent": id, "message": latest user text, "history": [...]}
    Response: JSON with a "reply" (or "response"/"message"/"text") field, or plain text.
    """
    headers = {}
    token = resolve_secret(agent.api_key_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    latest = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    resp = _post(agent.endpoint, headers, {"agent": agent.id, "message": latest, "history": history})
    try:
        data = resp.json()
    except ValueError:
        return resp.text
    if isinstance(data, dict):
        for key in ("reply", "response", "message", "text", "output"):
            if isinstance(data.get(key), str):
                return data[key]
    if isinstance(data, str):
        return data
    raise AgentError(f"Webhook reply has no 'reply' field: {resp.text[:300]}")


CONNECTORS = {
    KIND_GROK: _grok,
    KIND_CLAUDE: _claude,
    KIND_OPENAI: _openai_compatible,
    KIND_WEBHOOK: _webhook,
}


def send(agent: Agent, history: list[dict]) -> str:
    connector = CONNECTORS.get(agent.kind)
    if connector is None:
        raise AgentError(f"Unknown agent kind: {agent.kind}")
    if not agent.enabled:
        raise AgentError(f"{agent.name} is disabled.")
    return connector(agent, history)
