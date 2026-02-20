#!/bin/bash
# ──────────────────────────────────────────────────────────────
# deploy_agents.sh — Create / recreate agents in Azure AI Foundry
#
# Usage:
#   chmod +x deploy_agents.sh
#   ./deploy_agents.sh
#
# Prerequisites:
#   - az login (already authenticated)
#   - jq installed (brew install jq)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────
FOUNDRY_ENDPOINT="https://foundryPMAagentFramework.services.ai.azure.com/api/projects/proj-default"
MODEL_DEPLOYMENT="gpt-4.1"
ACA_ENDPOINT="https://prescriber-agent.happyflower-f99f5b75.westus3.azurecontainerapps.io/responses"
API_VERSION="2025-05-15-preview"

# ── Get access token ──────────────────────────────────────────
echo "🔑 Getting access token..."
TOKEN=$(az account get-access-token \
  --resource https://ai.azure.com \
  --query accessToken -o tsv 2>/dev/null || \
  az account get-access-token \
  --resource https://management.azure.com \
  --query accessToken -o tsv)

AUTH="Authorization: Bearer ${TOKEN}"
CT="Content-Type: application/json"

# ── Helper: list existing agents ──────────────────────────────
echo ""
echo "📋 Listing existing agents..."
EXISTING=$(curl -s "${FOUNDRY_ENDPOINT}/assistants?api-version=${API_VERSION}" \
  -H "${AUTH}" -H "${CT}")
echo "${EXISTING}" | python3 -m json.tool 2>/dev/null || echo "${EXISTING}"

# ── Create ContactLookupAgent ─────────────────────────────────
echo ""
echo "🤖 Creating ContactLookupAgent..."
CONTACT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "${FOUNDRY_ENDPOINT}/assistants?api-version=${API_VERSION}" \
  -H "${AUTH}" \
  -H "${CT}" \
  -d '{
    "model": "'"${MODEL_DEPLOYMENT}"'",
    "name": "ContactLookupAgent",
    "description": "Looks up publicly-known prescriber contact information (phone, address, NPI, specialty) using LLM general knowledge.",
    "instructions": "You are a medical-provider contact information assistant.\n\nWhen given a prescriber'\''s name (and optionally a state or city):\n1. Return any publicly known contact details including: full name and credentials, specialty, office phone, fax, office address, and NPI number.\n2. If you are not confident about specific details, say so explicitly.\n3. Always recommend verifying via the NPI Registry: https://npiregistry.cms.hhs.gov/\n4. Never fabricate phone numbers or addresses.\n5. Format the output clearly with labeled fields.",
    "temperature": 0.3,
    "top_p": 0.95
  }')

HTTP_CODE=$(echo "${CONTACT_RESPONSE}" | tail -1)
BODY=$(echo "${CONTACT_RESPONSE}" | sed '$d')

if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "201" ]]; then
  CONTACT_ID=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "✅ ContactLookupAgent created: ${CONTACT_ID}"
else
  echo "⚠️  ContactLookupAgent response (HTTP ${HTTP_CODE}):"
  echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}"
fi

# ── Create OrchestrationAgent ─────────────────────────────────
echo ""
echo "🤖 Creating OrchestrationAgent..."
ORCH_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "${FOUNDRY_ENDPOINT}/assistants?api-version=${API_VERSION}" \
  -H "${AUTH}" \
  -H "${CT}" \
  -d '{
    "model": "'"${MODEL_DEPLOYMENT}"'",
    "name": "OrchestrationAgent",
    "description": "Multi-agent orchestrator that combines Fabric Data Agent (Medicare Part D prescriber data) with Contact Lookup to answer prescriber questions.",
    "instructions": "You are a helpful medical-data assistant with two tools:\n\n1. **query_prescriber_data** — queries a Fabric Lakehouse containing Medicare Part D prescriber and drug data (prescriber names, states, drug names, total costs, claim counts, beneficiary counts, etc.).\n   Use this whenever the user asks about prescribers, drugs, costs, or claims.\n\n2. **lookup_prescriber_contact** — uses general knowledge to find publicly-known contact details for a prescriber (phone, address, NPI, specialty, etc.).\n   Use this when the user asks for contact info for a specific prescriber.\n\nWorkflow:\n- Decide which tool(s) to call based on the user'\''s question.\n- If the question involves both data AND contact info, call query_prescriber_data first, then lookup_prescriber_contact.\n- Combine all results into a clear, well-formatted answer.\n- Always cite the data source (Fabric Lakehouse or public records).\n- If a tool returns no data, say so honestly.",
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "query_prescriber_data",
          "description": "Query the Fabric Lakehouse for Medicare Part D prescriber and drug data. Use this tool whenever the user asks about prescribers, drugs, total costs, claim counts, beneficiary counts, or any other structured data.",
          "parameters": {
            "type": "object",
            "properties": {
              "question": {
                "type": "string",
                "description": "Natural-language question about prescribers, drugs, costs, or claims from the Medicare Part D Lakehouse data."
              }
            },
            "required": ["question"]
          }
        }
      },
      {
        "type": "function",
        "function": {
          "name": "lookup_prescriber_contact",
          "description": "Look up publicly-known contact information for a prescriber including phone number, office address, NPI, fax, email, and specialty.",
          "parameters": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "description": "Full name of the prescriber to look up (e.g. '\''John Smith'\'')"
              },
              "state": {
                "type": "string",
                "description": "US state abbreviation where the prescriber practices (e.g. '\''WA'\''). Optional but improves accuracy."
              }
            },
            "required": ["name"]
          }
        }
      }
    ],
    "temperature": 0.7,
    "top_p": 0.95
  }')

HTTP_CODE=$(echo "${ORCH_RESPONSE}" | tail -1)
BODY=$(echo "${ORCH_RESPONSE}" | sed '$d')

if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "201" ]]; then
  ORCH_ID=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "✅ OrchestrationAgent created: ${ORCH_ID}"
else
  echo "⚠️  OrchestrationAgent response (HTTP ${HTTP_CODE}):"
  echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  ACA Endpoint:  ${ACA_ENDPOINT}"
echo "  Foundry:       ${FOUNDRY_ENDPOINT}"
echo "  Model:         ${MODEL_DEPLOYMENT}"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "📋 Final agent list:"
curl -s "${FOUNDRY_ENDPOINT}/assistants?api-version=${API_VERSION}" \
  -H "${AUTH}" -H "${CT}" | python3 -m json.tool 2>/dev/null
