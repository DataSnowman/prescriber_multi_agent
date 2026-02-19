"""
Prescriber Multi-Agent Orchestrator

A workflow that combines:
  1. Fabric Data Agent — queries prescriber/drug data from a Fabric Lakehouse
  2. Contact Lookup   — uses ChatGPT to find prescriber contact information
  3. Orchestrator LLM — decides which tool(s) to call and synthesizes the answer

The orchestrator agent has two registered function-calling tools.  The LLM
autonomously decides which tool(s) to invoke based on the user's question,
collects results, and synthesizes a final answer.
"""

import asyncio
import os

from typing import Annotated

from agent_framework import (
    AgentRunEvent,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    TextContent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    WorkflowRunState,
    ai_function,
    handler,
)
from agent_framework.azure import AzureAIClient
from azure.identity.aio import DefaultAzureCredential
from typing_extensions import Never
from uuid import uuid4

from fabric_data_tool import FabricDataTool
from contact_lookup_tool import ContactLookupTool


# ---------------------------------------------------------------------------
# Function-calling tools (registered on the orchestrator LLM)
# ---------------------------------------------------------------------------

# Module-level singletons initialised once in run_interactive / run_workflow
_fabric_tool: FabricDataTool | None = None
_contact_tool: ContactLookupTool | None = None

_ORCHESTRATOR_INSTRUCTIONS = """\
You are a helpful medical-data assistant with two tools:

1. **query_prescriber_data** — queries a Fabric Lakehouse containing Medicare
   Part D prescriber and drug data (prescriber names, states, drug names,
   total costs, claim counts, beneficiary counts, etc.).
   Use this whenever the user asks about prescribers, drugs, costs, or claims.

2. **lookup_prescriber_contact** — uses ChatGPT's general knowledge to find
   publicly-known contact details for a prescriber (phone, address, NPI,
   specialty, etc.).
   Use this when the user asks for contact info for a specific prescriber.

Workflow:
- Decide which tool(s) to call based on the user's question.
- If the question involves both data AND contact info, call
  query_prescriber_data first to identify the prescriber, then call
  lookup_prescriber_contact with the prescriber's name (and state if known).
- Combine all results into a clear, well-formatted answer.
- Always cite the data source (Fabric Lakehouse or public records).
- If a tool returns no data, say so honestly.
"""


@ai_function
def query_prescriber_data(
    question: Annotated[
        str,
        "Natural-language question about prescribers, drugs, costs, or claims "
        "from the Medicare Part D Lakehouse data.",
    ],
) -> str:
    """Query the Fabric Lakehouse for Medicare Part D prescriber and drug data.

    Use this tool whenever the user asks about prescribers, drugs, total costs,
    claim counts, beneficiary counts, or any other structured data that lives
    in the Lakehouse.
    """
    if _fabric_tool is None:
        return "Fabric Data Agent is not initialised."
    print(f"[tool] query_prescriber_data → {question}")
    return _fabric_tool.client.ask(question, thread_name="multi-agent")


@ai_function
async def lookup_prescriber_contact(
    name: Annotated[
        str,
        "Full name of the prescriber to look up (e.g. 'John Smith').",
    ],
    state: Annotated[
        str,
        "US state abbreviation where the prescriber practices (e.g. 'WA'). "
        "Optional but improves accuracy.",
    ] = "",
) -> str:
    """Look up publicly-known contact information for a prescriber.

    Use this tool when the user asks for a prescriber's phone number,
    office address, NPI, fax, email, specialty, or other contact details.
    """
    if _contact_tool is None:
        return "Contact Lookup tool is not initialised."
    query = name
    if state:
        query += f" in {state}"
    print(f"[tool] lookup_prescriber_contact → {query}")
    return await _contact_tool._lookup(query)


class OrchestratorExecutor(Executor):
    """
    The orchestrator receives the user's question, routes it to the
    Fabric Data Agent for prescriber data, then to a Contact Lookup
    if needed, and finally asks the LLM to combine results into a
    coherent answer.
    """

    agent: ChatAgent

    def __init__(self, agent: ChatAgent, id: str = "orchestrator"):
        self.agent = agent
        super().__init__(id=id)

    @handler
    async def handle(self, messages: list[ChatMessage], ctx: WorkflowContext[str]) -> None:
        """
        Process user messages with the orchestrator LLM. The LLM has tool
        definitions for the Fabric Data Agent and Contact Lookup.
        """
        response = await self.agent.run(messages)

        # Forward the LLM's final text to downstream combiners or yield it
        final_text = response.text or "(No response from orchestrator)"
        print(f"[Orchestrator] {final_text[:200]}...")
        await ctx.send_message(final_text)


class ResultFormatterExecutor(Executor):
    """
    Terminal node that receives the orchestrator's combined answer and
    yields it as workflow output.
    """

    def __init__(self, id: str = "result-formatter"):
        super().__init__(id=id)

    @handler
    async def format_result(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(text)


async def run_workflow(question: str):
    """Build and run the multi-agent workflow for a single question."""

    global _fabric_tool, _contact_tool

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "")

    if not endpoint or not model:
        print("⚠️  FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT_NAME")
        print("   are not set.  The orchestrator LLM won't work without them.")
        print("   Update your .env file with your Azure AI Foundry project details.")
        return

    # Initialise the tool singletons so @ai_function wrappers can use them
    _fabric_tool = FabricDataTool()
    _contact_tool = ContactLookupTool()

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

        workflow = (
            WorkflowBuilder()
            .add_edge(orchestrator, formatter)
            .set_start_executor(orchestrator)
            .build()
        )

        print(f"\n{'='*60}")
        print(f"❓ Question: {question}")
        print(f"{'='*60}\n")

        async for event in workflow.run_stream(
            [ChatMessage(role="user", text=question)]
        ):
            if isinstance(event, WorkflowOutputEvent):
                print(f"\n💬 Answer:\n{'-'*50}")
                print(event.data)
                print(f"{'-'*50}")
            elif isinstance(event, WorkflowStatusEvent):
                if event.state == WorkflowRunState.IDLE:
                    pass  # workflow finished

    await asyncio.sleep(0.5)


async def run_interactive():
    """Interactive mode: prompt for questions in a loop."""

    global _fabric_tool, _contact_tool

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
    model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "")

    if not endpoint or not model:
        print("⚠️  FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT_NAME")
        print("   are not set.  Update your .env file first.")
        return

    # Initialise the tool singletons once so @ai_function wrappers can call them
    _fabric_tool = FabricDataTool()
    _contact_tool = ContactLookupTool()

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

        print("\n" + "=" * 60)
        print("🤖 Prescriber Multi-Agent Assistant — Ready!")
        print("   Tools: Fabric Data Agent (Lakehouse) + Contact Lookup (ChatGPT)")
        print("   Type 'quit' to exit")
        print("=" * 60)

        while True:
            print()
            sample = "Who is the top Lisinopril prescriber in WA and what is their contact info?"
            question = input(
                "❓ Ask a question (Enter for sample, 'quit' to exit): "
            ).strip()

            if not question:
                question = sample
                print(f"   Using sample: {question}")
            if question.lower() in ("quit", "exit"):
                print("👋 Goodbye!")
                break

            # The LLM autonomously decides which tools to call and
            # synthesises the final answer — no manual heuristics needed.
            print("\n🧠 Thinking…")

            workflow = (
                WorkflowBuilder()
                .add_edge(orchestrator, formatter)
                .set_start_executor(orchestrator)
                .build()
            )

            async for event in workflow.run_stream(
                [ChatMessage(role="user", text=question)]
            ):
                if isinstance(event, WorkflowOutputEvent):
                    print(f"\n💬 Answer:\n{'-'*50}")
                    print(event.data)
                    print(f"{'-'*50}")

    await asyncio.sleep(0.5)
