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
python3.12 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 2. Install dependencies
pip install --upgrade pip
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

### Just the Fabric Data Agent

```bash
python fabric_data_agent_client_prompt_for.py
```


Or press **F5** in VS Code using the "Agent Server (Inspector)" launch configuration.

## Azure Container Apps Deployment

### Prerequisites

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) logged in (`az login`)
- Docker (or [Azure Container Registry build](https://learn.microsoft.com/azure/container-registry/container-registry-tutorial-quick-task))

### 1. Build and push the container image

```bash
# Create a resource group and ACR (one-time)
az group create -n prescriber-rg -l eastus
az acr create -n prescriberacr -g prescriber-rg --sku Basic --admin-enabled true

# Build in ACR (no local Docker needed)
az acr build -r prescriberacr -t prescriber-agent:latest .
```

### 2. Create the Container App

```bash
# Create a Container Apps environment
az containerapp env create \
  -n prescriber-env -g prescriber-rg -l eastus

# Deploy
az containerapp create \
  -n prescriber-agent \
  -g prescriber-rg \
  --environment prescriber-env \
  --image prescriberacr.azurecr.io/prescriber-agent:latest \
  --registry-server prescriberacr.azurecr.io \
  --target-port 8080 \
  --ingress external \
  --env-vars \
    TENANT_ID=<your-tenant-id> \
    DATA_AGENT_URL=<your-data-agent-url> \
    FOUNDRY_PROJECT_ENDPOINT=<your-foundry-project-endpoint> \
    FOUNDRY_MODEL_DEPLOYMENT_NAME=gpt-4.1 \
  --min-replicas 0 \
  --max-replicas 3
```

### 3. Configure managed identity (recommended)

Instead of storing credentials as env vars, assign a managed identity so `DefaultAzureCredential` works automatically:

```bash
az containerapp identity assign -n prescriber-agent -g prescriber-rg --system-assigned
```

Then grant the identity access to your Azure AI Foundry project and Fabric workspace.

### How it works on ACA

- Azure Container Apps sets the `PORT` environment variable automatically.
- When `PORT` is set and no CLI flags are given, the app auto-detects server mode — no `--server` flag needed in the Dockerfile.
- The `Dockerfile` runs `python app.py --server` explicitly for clarity.
- Interactive mode (`python app.py`) still works locally as before — it is unaffected by the ACA changes.

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
