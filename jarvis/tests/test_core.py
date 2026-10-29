import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import connectors  # noqa: E402
from core.jarvis import agent_history, handle  # noqa: E402
from core.models import KIND_GROK, KIND_WEBHOOK, Agent, Message  # noqa: E402
from core.router import route  # noqa: E402
from core.store import Store  # noqa: E402

GROK = Agent(id="grok", name="Grok Mail", kind=KIND_GROK, skills=["email", "inbox", "gmail"])
CAL = Agent(id="calendar", name="Calendar", kind=KIND_WEBHOOK, skills=["meeting", "schedule"], endpoint="http://x")


# Router

def test_mention_wins_and_is_stripped():
    r = route("@calendar what about my email?", [GROK, CAL])
    assert r.agent.id == "calendar"
    assert r.text == "what about my email?"


def test_keywords_route():
    assert route("summarize my unread emails", [GROK, CAL]).agent.id == "grok"
    assert route("schedule a meeting tomorrow", [GROK, CAL]).agent.id == "calendar"


def test_brain_used_when_keywords_tie():
    brain = mock.Mock(return_value="calendar")
    r = route("help me plan tomorrow", [GROK, CAL], default_id="grok", brain=brain)
    assert r.agent.id == "calendar" and "brain" in r.reason


def test_bad_brain_answer_falls_back_to_default():
    r = route("hello", [GROK, CAL], default_id="grok", brain=lambda _: "nonsense")
    assert r.agent.id == "grok" and r.reason == "default agent"


def test_disabled_agents_ignored():
    off = Agent(id="grok", name="Grok", kind=KIND_GROK, skills=["email"], enabled=False)
    assert route("@grok email", [off, CAL]).agent.id == "calendar"
    assert route("x", [off]).agent is None


# Store

def test_store_seeds_defaults_and_roundtrips(tmp_path):
    store = Store(tmp_path)
    assert [a.id for a in store.agents()] == ["grok", "finance"]
    store.upsert_agent(CAL)
    assert {a.id for a in Store(tmp_path).agents()} == {"grok", "finance", "calendar"}
    store.delete_agent("calendar")
    assert [a.id for a in store.agents()] == ["grok", "finance"]
    store.save_settings({**store.settings(), "owner_name": "KP"})
    assert Store(tmp_path).settings()["owner_name"] == "KP"


def test_api_key_never_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret-value")
    store = Store(tmp_path)
    store.agents()
    assert "secret-value" not in (tmp_path / "agents.json").read_text()


# History

def test_agent_history_pairs_only_successful_turns():
    msgs = [
        Message("user", "a", agent_id="grok"), Message("agent", "A", agent_id="grok"),
        Message("user", "b", agent_id="calendar"), Message("agent", "B", agent_id="calendar"),
        Message("user", "c", agent_id="grok"), Message("agent", "boom", agent_id="grok", error=True),
        Message("user", "d", agent_id="grok"), Message("agent", "D", agent_id="grok"),
    ]
    assert agent_history(msgs, "grok", 6) == [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "A"},
        {"role": "user", "content": "d"}, {"role": "assistant", "content": "D"},
    ]
    assert agent_history(msgs, "grok", 1) == [
        {"role": "user", "content": "d"}, {"role": "assistant", "content": "D"},
    ]


# Connectors

def fake_response(status=200, json_data=None, text=""):
    resp = mock.Mock(status_code=status, text=text or str(json_data))
    resp.json.return_value = json_data
    return resp


def test_grok_sends_system_prompt_and_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k")
    agent = Agent(id="grok", name="G", kind=KIND_GROK, model="grok-4", api_key_env="XAI_API_KEY", system_prompt="be brief")
    with mock.patch("requests.post", return_value=fake_response(json_data={"choices": [{"message": {"content": "hi"}}]})) as post:
        assert connectors.send(agent, [{"role": "user", "content": "yo"}]) == "hi"
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://api.x.ai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer k"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "be brief"}


def test_pick_latest_grok():
    ids = ["grok-3", "grok-4-0709", "grok-4.1-fast", "grok-4.6", "grok-4.5", "grok-2-vision"]
    assert connectors.pick_latest_grok(ids) == "grok-4.6"
    assert connectors.pick_latest_grok(["grok-4-1-fast", "grok-4-0709"]) == "grok-4-1-fast"
    assert connectors.pick_latest_grok(["other"]) == ""


def test_grok_blank_model_resolves_latest(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k")
    connectors._latest_grok_cache.clear()
    agent = Agent(id="grok", name="G", kind=KIND_GROK, model="", api_key_env="XAI_API_KEY")
    models = fake_response(json_data={"data": [{"id": "grok-4.5"}, {"id": "grok-4.6"}]})
    models.raise_for_status = mock.Mock()
    chat = fake_response(json_data={"choices": [{"message": {"content": "hi"}}]})
    with mock.patch("requests.get", return_value=models), mock.patch("requests.post", return_value=chat) as post:
        assert connectors.send(agent, [{"role": "user", "content": "yo"}]) == "hi"
    assert post.call_args.kwargs["json"]["model"] == "grok-4.6"


def test_finance_requests_route_to_finance():
    from core.models import default_agents
    agents = default_agents()
    assert route("how much did I spend on food?", agents).agent.id == "finance"
    assert route("summarize my unread emails", agents).agent.id == "grok"


def test_grok_missing_key_is_clear_error(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    agent = Agent(id="grok", name="G", kind=KIND_GROK, api_key_env="XAI_API_KEY")
    with pytest.raises(connectors.AgentError, match="XAI_API_KEY"):
        connectors.send(agent, [{"role": "user", "content": "yo"}])


def test_webhook_reply_shapes():
    with mock.patch("requests.post", return_value=fake_response(json_data={"reply": "done"})) as post:
        assert connectors.send(CAL, [{"role": "user", "content": "go"}]) == "done"
    assert post.call_args.kwargs["json"]["message"] == "go"
    with mock.patch("requests.post", return_value=fake_response(500, text="down")):
        with pytest.raises(connectors.AgentError, match="HTTP 500"):
            connectors.send(CAL, [{"role": "user", "content": "go"}])


# Orchestrator

def test_handle_records_exchange_and_errors(tmp_path):
    store = Store(tmp_path)
    store.upsert_agent(CAL)
    with mock.patch.object(connectors, "send", return_value="booked"):
        user, reply = handle(store, "schedule a meeting")
    assert reply.agent_id == "calendar" and reply.content == "booked" and not reply.error
    with mock.patch.object(connectors, "send", side_effect=connectors.AgentError("nope")):
        _, reply = handle(store, "check inbox")
    assert reply.agent_id == "grok" and reply.error
    assert len(store.messages()) == 4
