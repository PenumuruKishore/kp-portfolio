# 🛰️ Jarvis

One interface to command all your AI agents. You talk to Jarvis, and Jarvis
hands each request to the agent best suited for it. Grok Mail (your Gmail
agent) is set up out of the box.

## Run it

```bash
pip install -r jarvis/requirements.txt
cp jarvis/.streamlit/secrets.toml.example jarvis/.streamlit/secrets.toml   # fill in keys
cd jarvis && streamlit run app.py
```

On Streamlit Cloud, point a new app at `jarvis/app.py` and paste the secrets
into **App settings → Secrets**. **Always set `JARVIS_PASSWORD`:** without it,
anyone who finds the URL can command your agents, including your email.

## Pages

- **Command Center**: chat with Jarvis. Leave "Auto" on and Jarvis routes for
  you, pick an agent, or `@mention` one (`@grok what needs a reply?`). Each
  agent's quick actions are one click away.
- **Agents**: add, edit, test or disable agents.
- **Activity**: every task, which agent did it, why it was routed there, and
  whether it succeeded.
- **Settings**: default agent, the optional "brain", and how much past
  conversation each agent sees.

## How routing works

1. An `@mention` always wins.
2. Otherwise, the agent whose **skills** keywords best match the request.
3. If nothing matches clearly and you've set a **Jarvis brain** (any LLM
   agent), it picks the agent.
4. Otherwise, the **default agent**.

## Agent types

| Type | Use it for | Needs |
|---|---|---|
| Grok (xAI API) | Grok models | `XAI_API_KEY` |
| Claude (Anthropic API) | Claude models | `ANTHROPIC_API_KEY` |
| OpenAI-compatible | OpenAI, Groq, Ollama, LM Studio… | base URL + key |
| Custom webhook | A bot you run yourself (with its own tools) | URL, optional bearer token |

API keys are read from environment variables or Streamlit secrets. Jarvis
stores only the secret's *name*, never the key.

### Connecting your existing Grok Gmail bot

The built-in Grok Mail agent calls the xAI API directly with an email-assistant
prompt. That gives you Grok's reasoning but **not your Gmail**: the model can't
see your inbox on its own. If your Grok bot already runs as a service with
Gmail access, switch the agent's type to **Custom webhook** and point it at
that service. Jarvis will POST:

```json
{"agent": "grok", "message": "Summarize my unread emails", "history": [{"role": "user", "content": "..."}]}
```

and expects back `{"reply": "..."}` (or plain text). Set **Secret name** to an
env var holding a bearer token so only Jarvis can call your bot.

## Tests

```bash
cd jarvis && python -m pytest -q tests
```

Data (agents, history, settings) lives in `jarvis/data/` (git-ignored), or in
`$JARVIS_DATA_DIR` if set.
