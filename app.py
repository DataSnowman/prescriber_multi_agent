#!/usr/bin/env python3
"""
Prescriber Multi-Agent — Main Entrypoint

Combines a Fabric Data Agent (prescriber/drug data) with a Contact Lookup tool
and an orchestrator LLM to answer questions like:
  "Who is the top Lisinopril prescriber in WA and what is their contact info?"

Supports:
  --interactive   Interactive prompt loop (default)
  --server        HTTP server mode for Agent Inspector / production
  --question "…"  Answer a single question and exit
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from orchestrator import run_interactive, run_workflow


def main():
    parser = argparse.ArgumentParser(
        description="Prescriber Multi-Agent: Fabric Data + Contact Lookup"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--interactive",
        action="store_true",
        default=True,
        help="Interactive prompt loop (default)",
    )
    group.add_argument(
        "--question", "-q",
        type=str,
        help="Answer a single question and exit",
    )
    group.add_argument(
        "--server",
        action="store_true",
        help="Run as HTTP server (for Agent Inspector / deployment)",
    )

    args = parser.parse_args()

    if args.server:
        _run_server()
    elif args.question:
        asyncio.run(run_workflow(args.question))
    else:
        asyncio.run(run_interactive())


def _run_server():
    """Start the agent as an HTTP server for Agent Inspector."""
    try:
        from agent_framework import ChatMessage, WorkflowBuilder
        from agent_framework.azure import AzureAIClient
        from azure.identity.aio import DefaultAzureCredential
        from azure.ai.agentserver.agentframework import from_agent_framework

        from orchestrator import (
            OrchestratorExecutor,
            ResultFormatterExecutor,
            _ORCHESTRATOR_INSTRUCTIONS,
            query_prescriber_data,
            lookup_prescriber_contact,
        )
        from fabric_data_tool import FabricDataTool
        from contact_lookup_tool import ContactLookupTool
        import orchestrator as _orch

        endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
        model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "")

        if not endpoint or not model:
            print("⚠️  Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT_NAME in .env")
            sys.exit(1)

        async def build_and_serve():
            # Initialise tool singletons for the @ai_function wrappers
            _orch._fabric_tool = FabricDataTool()
            _orch._contact_tool = ContactLookupTool()

            async with (
                DefaultAzureCredential() as credential,
                AzureAIClient(
                    project_endpoint=endpoint,
                    model_deployment_name=model,
                    credential=credential,
                ).create_agent(
                    name="OrchestratorAgent",
                    instructions=_ORCHESTRATOR_INSTRUCTIONS,
                    tools=[query_prescriber_data, lookup_prescriber_contact],
                ) as orchestrator_agent,
            ):
                orchestrator = OrchestratorExecutor(orchestrator_agent)
                formatter = ResultFormatterExecutor()

                agent = (
                    WorkflowBuilder()
                    .add_edge(orchestrator, formatter)
                    .set_start_executor(orchestrator)
                    .build()
                    .as_agent()
                )

                await from_agent_framework(agent).run_async()

        asyncio.run(build_and_serve())

    except ImportError as e:
        print(f"❌ Missing server dependencies: {e}")
        print("   pip install azure-ai-agentserver-core==1.0.0b10 azure-ai-agentserver-agentframework==1.0.0b10")
        sys.exit(1)


if __name__ == "__main__":
    main()
