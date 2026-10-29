"""Jarvis: one place to command all of Kishore's AI agents.

Run with:  streamlit run jarvis/app.py
"""

from __future__ import annotations

import hmac
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import connectors  # noqa: E402
from core.jarvis import handle  # noqa: E402
from core.models import KIND_CLAUDE, KIND_GROK, KIND_LABELS, KIND_OPENAI, KIND_WEBHOOK, Agent, slugify  # noqa: E402
from core.store import Store  # noqa: E402

st.set_page_config(page_title="Jarvis", page_icon="🛰️", layout="wide")

KIND_DEFAULTS = {
    KIND_GROK: {"endpoint": "https://api.x.ai/v1", "model": "", "api_key_env": "XAI_API_KEY"},
    KIND_CLAUDE: {"endpoint": "", "model": "claude-opus-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
    KIND_OPENAI: {"endpoint": "https://api.openai.com/v1", "model": "", "api_key_env": "OPENAI_API_KEY"},
    KIND_WEBHOOK: {"endpoint": "https://", "model": "", "api_key_env": ""},
}


def require_login() -> None:
    """Gate the app behind JARVIS_PASSWORD, since it can act on your accounts."""
    password = connectors.resolve_secret("JARVIS_PASSWORD")
    if not password:
        st.sidebar.warning("No `JARVIS_PASSWORD` set: anyone who can open this app can command your agents.")
        return
    if st.session_state.get("authed"):
        return
    st.title("🛰️ Jarvis")
    attempt = st.text_input("Password", type="password")
    if attempt and hmac.compare_digest(attempt, password):
        st.session_state.authed = True
        st.rerun()
    elif attempt:
        st.error("Wrong password.")
    st.stop()


def greeting(name: str) -> str:
    hour = datetime.now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    return f"Good {part}, {name}."


def agent_label(agent: Agent | None) -> str:
    return f"{agent.icon} {agent.name}" if agent else "⚠️ Jarvis"


def dispatch(store: Store, text: str, agent_id: str) -> None:
    with st.spinner("Working on it…"):
        handle(store, text, agent_id)
    st.rerun()


# Pages

def command_center(store: Store) -> None:
    settings = store.settings()
    agents = store.agents()
    by_id = {a.id: a for a in agents}
    enabled = [a for a in agents if a.enabled]

    st.title("🛰️ Jarvis")
    st.caption(greeting(settings["owner_name"]) + " Tell me what you need, or @mention an agent directly.")

    cols = st.columns(max(len(enabled), 1))
    for col, agent in zip(cols, enabled):
        ok, status = connectors.is_configured(agent)
        col.metric(agent_label(agent), "Online" if ok else "Needs setup", help=status, delta_color="off")

    options = ["auto"] + [a.id for a in enabled]
    target = st.radio(
        "Send to",
        options,
        format_func=lambda i: "✨ Auto (Jarvis decides)" if i == "auto" else agent_label(by_id[i]),
        horizontal=True,
    )
    forced = "" if target == "auto" else target

    actions = [(a, q) for a in enabled for q in a.quick_actions if not forced or a.id == forced]
    if actions:
        st.write("**Quick actions**")
        qcols = st.columns(min(len(actions), 3))
        for i, (agent, action) in enumerate(actions):
            if qcols[i % len(qcols)].button(f"{agent.icon} {action}", key=f"qa-{agent.id}-{i}", use_container_width=True):
                dispatch(store, action, agent.id)

    st.divider()
    for m in store.messages()[-60:]:
        agent = by_id.get(m.agent_id)
        if m.role == "user":
            with st.chat_message("user", avatar="🧑"):
                st.markdown(m.content)
        else:
            with st.chat_message("assistant", avatar=agent.icon if agent else "🛰️"):
                meta = f"{agent_label(agent)} · {m.route_reason}" if agent else "Jarvis"
                if m.latency_ms:
                    meta += f" · {m.latency_ms / 1000:.1f}s"
                st.caption(meta)
                (st.error if m.error else st.markdown)(m.content)

    if prompt := st.chat_input("Ask Jarvis…"):
        dispatch(store, prompt, forced)


def agent_form(store: Store, agent: Agent, is_new: bool) -> None:
    key = f"new-{agent.kind}" if is_new else agent.id
    with st.form(f"form-{key}"):
        c1, c2 = st.columns([1, 4])
        icon = c1.text_input("Icon", agent.icon, key=f"icon-{key}")
        name = c2.text_input("Name", agent.name, key=f"name-{key}")
        kind = st.selectbox(
            "Type", list(KIND_LABELS), index=list(KIND_LABELS).index(agent.kind),
            format_func=KIND_LABELS.get, key=f"kind-{key}",
        )
        description = st.text_input("What it does", agent.description, key=f"desc-{key}")
        skills = st.text_input(
            "Skills (comma-separated keywords that route requests here)",
            ", ".join(agent.skills), key=f"skills-{key}",
        )
        c3, c4 = st.columns(2)
        endpoint = c3.text_input("Endpoint / base URL", agent.endpoint, key=f"ep-{key}")
        model = c4.text_input("Model (blank = newest Grok)" if agent.kind == KIND_GROK else "Model", agent.model, key=f"model-{key}")
        api_key_env = st.text_input(
            "Secret name (env var or Streamlit secret holding the API key/token; never the key itself)",
            agent.api_key_env, key=f"secret-{key}",
        )
        system_prompt = st.text_area("Instructions (system prompt)", agent.system_prompt, key=f"sys-{key}")
        quick = st.text_area("Quick actions (one per line)", "\n".join(agent.quick_actions), key=f"qa-{key}")
        enabled = st.checkbox("Enabled", agent.enabled, key=f"en-{key}")
        saved = st.form_submit_button("Add agent" if is_new else "Save", type="primary")

    if saved:
        if not name.strip():
            st.error("Give the agent a name.")
            return
        new_id = agent.id
        if is_new:
            new_id = slugify(name)
            existing = {a.id for a in store.agents()}
            n = 2
            while new_id in existing:
                new_id, n = f"{slugify(name)}-{n}", n + 1
        defaults = KIND_DEFAULTS[kind] if is_new else {}
        store.upsert_agent(Agent(
            id=new_id, name=name.strip(), kind=kind, icon=icon or "🤖",
            description=description.strip(),
            skills=[s.strip() for s in skills.split(",") if s.strip()],
            quick_actions=[q.strip() for q in quick.splitlines() if q.strip()],
            endpoint=endpoint.strip() or defaults.get("endpoint", ""),
            model=model.strip() or defaults.get("model", ""),
            api_key_env=api_key_env.strip() or defaults.get("api_key_env", ""),
            system_prompt=system_prompt.strip(), enabled=enabled,
        ))
        st.success(f"Saved {name}.")
        st.rerun()


def agents_page(store: Store) -> None:
    st.title("🤖 Agents")
    st.caption("Your roster. Jarvis routes each request to the agent whose skills match, or to the one you @mention.")

    for agent in store.agents():
        ok, status = connectors.is_configured(agent)
        badge = "🟢" if ok and agent.enabled else "⚪" if not agent.enabled else "🟠"
        with st.expander(f"{badge} {agent_label(agent)}  ·  `{agent.handle}`  ·  {KIND_LABELS[agent.kind]}"):
            st.write(agent.description or "_No description._")
            st.caption(f"Status: {status}")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Test connection", key=f"test-{agent.id}"):
                with st.spinner("Pinging…"):
                    try:
                        reply = connectors.send(agent, [{"role": "user", "content": "Reply with one word: online"}])
                        st.success(f"Replied: {reply[:200]}")
                    except connectors.AgentError as exc:
                        st.error(str(exc))
            if b2.button("Delete", key=f"del-{agent.id}"):
                store.delete_agent(agent.id)
                st.rerun()
            agent_form(store, agent, is_new=False)

    st.subheader("Add an agent")
    kind = st.selectbox("Type", list(KIND_LABELS), format_func=KIND_LABELS.get, key="new-kind-pick")
    agent_form(store, Agent(name="", kind=kind, **KIND_DEFAULTS[kind]), is_new=True)


def activity_page(store: Store) -> None:
    st.title("📜 Activity")
    agents = {a.id: a for a in store.agents()}
    messages = store.messages()
    replies = [m for m in messages if m.role in ("agent", "system")]
    if not replies:
        st.info("Nothing yet. Send Jarvis a request from the Command Center.")
        return

    cols = st.columns(len(agents) + 1)
    cols[0].metric("Total tasks", len(replies))
    for col, agent in zip(cols[1:], agents.values()):
        mine = [m for m in replies if m.agent_id == agent.id]
        failed = sum(m.error for m in mine)
        col.metric(agent_label(agent), len(mine), f"{failed} failed" if failed else None, delta_color="inverse")

    requests_by_reply = {}
    for prev, cur in zip(messages, messages[1:]):
        if prev.role == "user" and cur.role != "user":
            requests_by_reply[cur.id] = prev.content
    st.dataframe(
        [
            {
                "When": datetime.fromtimestamp(m.ts).strftime("%b %d %H:%M"),
                "Agent": agent_label(agents.get(m.agent_id)),
                "Request": requests_by_reply.get(m.id, "")[:80],
                "Status": "❌ Failed" if m.error else "✅ Done",
                "Routed because": m.route_reason,
                "Seconds": round(m.latency_ms / 1000, 1),
            }
            for m in reversed(replies)
        ],
        use_container_width=True, hide_index=True,
    )


def settings_page(store: Store) -> None:
    st.title("⚙️ Settings")
    settings = store.settings()
    agents = store.agents()
    ids = [a.id for a in agents]
    names = {a.id: agent_label(a) for a in agents}

    with st.form("settings"):
        owner = st.text_input("Your name", settings["owner_name"])
        default = st.selectbox(
            "Default agent (used when nothing else matches)", ids,
            index=ids.index(settings["default_agent"]) if settings["default_agent"] in ids else 0,
            format_func=names.get,
        ) if ids else ""
        brain_opts = [""] + [a.id for a in agents if a.kind != KIND_WEBHOOK]
        brain = st.selectbox(
            "Jarvis brain: an LLM agent that routes requests no keyword matches (optional)",
            brain_opts,
            index=brain_opts.index(settings["brain_agent"]) if settings["brain_agent"] in brain_opts else 0,
            format_func=lambda i: "Off" if not i else names[i],
        )
        turns = st.slider("Past exchanges sent to an agent as context", 0, 20, int(settings["context_turns"]))
        if st.form_submit_button("Save", type="primary"):
            store.save_settings({"owner_name": owner, "default_agent": default, "brain_agent": brain, "context_turns": turns})
            st.success("Saved.")

    st.divider()
    if st.button("Clear conversation history"):
        store.clear_messages()
        st.success("History cleared.")


def main() -> None:
    require_login()
    store = Store()
    pages = {
        "🛰️ Command Center": command_center,
        "🤖 Agents": agents_page,
        "📜 Activity": activity_page,
        "⚙️ Settings": settings_page,
    }
    choice = st.sidebar.radio("Jarvis", list(pages), label_visibility="collapsed")
    st.sidebar.divider()
    for agent in store.agents():
        ok, _ = connectors.is_configured(agent)
        st.sidebar.caption(f"{'🟢' if ok and agent.enabled else '🟠'} {agent_label(agent)} `{agent.handle}`")
    pages[choice](store)


main()
