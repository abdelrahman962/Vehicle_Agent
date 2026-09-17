# Vehicle Agent

A conversational AI agent for querying a Pitstrack vehicle fleet — ask questions in plain English, get answers backed by live fleet data.

![Python](https://img.shields.io/badge/python-3.14-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688)
![LangChain](https://img.shields.io/badge/LangChain-1.4-1C3C3C)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)
![Streamlit](https://img.shields.io/badge/Streamlit-1.64-FF4B4B)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Running the App](#running-the-app)
- [What the Agent Can Do](#what-the-agent-can-do)
- [Design Notes](#design-notes)
- [Known Limitations](#known-limitations)

---

## Overview

Vehicle Agent wraps the Pitstrack vehicle-tracking API behind a small FastAPI service, exposes it to a local LLM as a set of LangChain tools, and serves the whole thing through a Streamlit chat interface. Ask things like:

> "How many vehicles have an expired license?"
> "Show me vehicles with color white."
> "Which vehicles are diesel and sorted by tank capacity?"

...and the agent calls the right tool, queries the fleet, and renders the answer as a table, chart, or short summary — never raw JSON.

## Architecture

```
┌─────────────────┐     chat messages      ┌──────────────────────┐
│  Streamlit UI    │ ─────────────────────▶ │   LangGraph Agent     │
│ (streamlit_app)  │ ◀───────────────────── │  (ChatOllama + tools) │
└─────────────────┘     rendered results    └───────────┬──────────┘
                                                          │ tool calls (HTTP)
                                                          ▼
                                             ┌──────────────────────┐
                                             │   FastAPI service    │
                                             │      (main.py)       │
                                             └───────────┬──────────┘
                                                          │
                                                          ▼
                                             ┌──────────────────────┐
                                             │   VehicleService      │
                                             │     (service.py)     │
                                             │ filter / sort / group │
                                             └───────────┬──────────┘
                                                          │ cached 90s
                                                          ▼
                                             ┌──────────────────────┐
                                             │   Pitstrack API       │
                                             │  (live fleet data)    │
                                             └──────────────────────┘
```

Conversation memory persists per browser session via a LangGraph `MySQLSaver` checkpointer, keyed by a `thread_id`.

## Project Structure

```
VehicleAgent/
├── .env                        # API tokens, MySQL config, LangSmith keys
├── requirements.txt            # pinned dependency versions
├── app/
│   └── agent/
│       └── memory.py           # LangGraph MySQL checkpointer (conversation memory)
└── pitstrack_api/
    ├── service.py               # core data logic: filter, sort, group, cache
    ├── main.py                  # FastAPI endpoints (/vehicles, /count-by, /group-by)
    ├── langchain_tools.py       # LangChain @tool wrappers calling the FastAPI service
    ├── agent.py                 # builds the LangGraph agent (model + tools + memory)
    ├── agent_instructions.md    # system prompt: field mappings, tool-selection rules
    └── streamlit_app.py         # chat UI + display-layer bug fixes
```

## Setup

**Prerequisites:** Python 3.14, a running MySQL instance, [Ollama](https://ollama.com) with `qwen3:1.7b` pulled, and VPN/network access to the Pitstrack API.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
ollama pull qwen3:1.7b
```

Configure `.env` at the project root:

```env
PITSTRACK_API_URL=...
PITSTRACK_TOKEN=...              # JWT — expires periodically, refresh manually
PITSTRACK_ACCOUNT=...

MYSQL_HOST=...
MYSQL_PORT=...
MYSQL_DATABASE=...
MYSQL_USERNAME=...
MYSQL_PASSWORD=...

LANGSMITH_TRACING=true           # optional, for tracing
LANGSMITH_API_KEY=...
LANGSMITH_ENDPOINT=...
LANGSMITH_PROJECT=vehicle-agent
```

## Running the App

Two processes, in order:

```bash
# 1. Start the FastAPI service (must be running first)
.venv\Scripts\python.exe -m uvicorn pitstrack_api.main:app --port 8000

# 2. Start the chat UI
.venv\Scripts\python.exe -m streamlit run pitstrack_api\streamlit_app.py
```

Open the Streamlit URL printed in the terminal and start chatting.

## What the Agent Can Do

| Tool | Purpose |
|---|---|
| `get_vehicles` | List/filter/sort vehicles, with field trimming and `in`/`not in` support |
| `get_vehicles_count` | Total count matching an optional filter |
| `get_vehicle_details` | Full details of one specific vehicle by id or name |
| `get_vehicle_counts_by_field` | Counts grouped by a field's value (e.g. per fuel type) |
| `get_vehicles_grouped_by_field` | Actual vehicles grouped by a field's value, with details |

Supported filter operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `like`, `not like`, `in`, `not in`.

## Design Notes

A few choices exist specifically because of failures found during live testing against the real API and model:

- **`interrupt_after=["tools"]`** stops the agent right after a tool call instead of letting it generate a free-form final answer. Removing it once caused a 273-second hallucinated response — it is load-bearing, not stylistic.
- **Deterministic display fixes over more prompt engineering.** The 1.7B model reliably mis-selects `get_vehicles_grouped_by_field` for single-value questions (e.g. "vehicles with color white") even with explicit counter-examples in its instructions. Rather than keep tuning prose, `streamlit_app.py` detects this case and narrows the display itself.
- **Pagination is handled outside the LLM.** "Give me another 5 vehicles" is answered by a deterministic exclusion filter built from previously-shown ids, bypassing the agent entirely — the model could not reliably reconstruct this from conversation history.
- **A single `get_vehicles` tool**, not split into `list/find/sort/count` variants, to avoid adding more tool-selection ambiguity for a small non-reasoning model.

## Known Limitations

These are model-capacity limits observed through repeated live testing, not implementation bugs:

- Pronoun/scope resolution on some follow-ups ("sort them by name") is inconsistent.
- Meta-conversational questions ("what have I asked you?") can be nondeterministic.
- Rare cases of confidently substituting a different real vehicle instead of reporting "not found."
- A larger local model (`qwen3.5:9b`) was tried and performed worse across every axis (no real tool calls, wrong field selection, ~275s latency) — reverted.
