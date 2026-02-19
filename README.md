# Prescriber Multi-Agent

A multi-agent application that combines a **Microsoft Fabric Data Agent** (Medicare Part D prescriber data) with a **Contact Lookup** tool, orchestrated by an **Azure AI Foundry LLM**.

## Architecture

```
User Question
     │
     ▼
┌─────────────┐
│ Orchestrator │  (Azure AI Foundry — gpt-4o)
│    LLM       │
└──┬───────┬──┘
   │       │
   ▼       ▼
┌──────┐ ┌────────────┐
│Fabric│ │  Contact   │
│ Data │ │  Lookup    │
│Agent │ │  (mock)    │
└──────┘ └────────────┘
   │           │
   └─────┬─────┘
         ▼
   Combined Answer
```

### Components

| File | Role |
|---|---|
| `app.py` | Main entrypoint — interactive, single-question, or server mode |
| `orchestrator.py` | Workflow that routes questions through Fabric + Contact agents |
| `fabric_data_tool.py` | Wraps the existing `FabricDataAgentClient` as an Agent Framework Executor |
| `contact_lookup_tool.py` | Mock contact lookup (replace with your real data source) |

## Prerequisites

- Python 3.10+
- An Azure account with:
  - A **Microsoft Fabric** workspace containing a published Data Agent
  - An **Azure AI Foundry** project with a deployed model (e.g. `gpt-4o`)
- Azure CLI logged in (`az login`)

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env        # or edit .env directly
# Fill in FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT_NAME
```

### Environment Variables

| Variable | Description |
|---|---|
| `TENANT_ID` | Azure AD tenant ID for Fabric auth |
| `DATA_AGENT_URL` | Full Fabric Data Agent OpenAI-compatible endpoint |
| `FOUNDRY_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | Deployed model name (e.g. `gpt-4o`) |

## Usage

### Interactive Mode (default)

```bash
python app.py
# or
python app.py --interactive
```

Type questions at the prompt. Type `new` to start a fresh thread, `quit` to exit.

### Single Question

```bash
python app.py --question "Who is the top Lisinopril prescriber in WA?"
```

### Server Mode (Agent Inspector)

```bash
python app.py --server
```

Or press **F5** in VS Code using the "Agent Server (Inspector)" launch configuration.

## Debugging

The `.vscode/launch.json` includes three debug configurations:

- **Interactive Mode** — step through the interactive prompt loop
- **Single Question** — debug a one-shot question
- **Agent Server (Inspector)** — starts the Agent Inspector then launches the server

## Customisation

### Replace the Contact Lookup

Edit `contact_lookup_tool.py` and replace the `_MOCK_CONTACTS` dictionary with a real data source (database query, API call, etc.).

### Add More Tools

1. Create a new Executor in its own file
2. Wire it into the orchestrator's `run_workflow()` function
3. Update the orchestrator LLM instructions to describe the new capability

## License

MIT
